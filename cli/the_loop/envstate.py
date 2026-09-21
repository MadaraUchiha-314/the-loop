"""What the env file declares, what a running process holds, and where they differ.

A harness session's environment is whatever tmux handed its pane when the pane was
forked, and nothing re-reads it afterwards — so a credential rotation leaves the service
on the new value and every running session on the old one (issue-410). This module is
the knowledge that makes the drift sayable: the file's current contents, one process's
actual environment, and the comparison of the two.

Three rules govern everything here:

* **The file is re-read, never remembered.** :func:`declared` parses ``env.file`` at the
  moment it is called. ``os.environ`` is deliberately not consulted: this process loaded
  the file once, at start, under :func:`envfile.load`'s "a name already set wins" rule —
  which is exactly how it comes to be holding the value that was retired.
* **A value is never spoken.** Output identifies a value by :func:`fingerprint` and by
  nothing else. "These two processes hold different tokens" is the whole of what the
  operator needs, and it is sayable without saying either token.
* **Reading another process never raises.** A pid that has exited, a permission denial,
  a platform with neither ``/proc`` nor a usable ``ps`` — all of them are ``None``, which
  callers report as *unverified* rather than as drift.

Spec: docs/specs/issue-410/design.md.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple

from . import envfile

logger = logging.getLogger("the-loop.envstate")

__all__ = [
    "FINGERPRINT_LENGTH",
    "compare",
    "declared",
    "environ_matches_declared",
    "fingerprint",
    "process_environ",
    "spawn_environment",
]

#: How much of the digest is shown. Long enough that two live credentials will not
#: collide, short enough to read at a glance in a table — and a one-way function of a
#: high-entropy secret either way, which is what makes printing it safe at all.
FINGERPRINT_LENGTH = 8

#: How long ``ps`` gets to answer. It is a fallback on a platform without ``/proc``;
#: a hung ``ps`` must degrade to "unverified", never hold up a restart.
_PS_TIMEOUT_SECONDS = 10


def fingerprint(value: str) -> str:
    """A short, one-way identifier for ``value`` — the only form output may take.

    Two processes holding the same secret fingerprint alike; two holding different
    secrets do not. Nothing about the value itself survives: not its length, not its
    prefix, not its shape.
    """
    return hashlib.sha256(value.encode("utf-8", "surrogateescape")).hexdigest()[
        :FINGERPRINT_LENGTH
    ]


def declared(
    config: Mapping, config_path: Path
) -> Optional[Tuple[Dict[str, str], Tuple[int, ...]]]:
    """What ``env.file`` declares **right now**, or ``None`` when it names no file.

    The values and the 1-based numbers of the lines that were skipped — the numbers
    because a malformed line's *text* may itself be a secret (``envfile``'s rule).

    ``None`` is "the config names no env file", which is the state ``sessions restart``
    refuses on: there is no declared environment to roll onto, and a respawn for nothing
    still costs the operator every pane. It is deliberately distinct from an empty
    mapping, which is a file that is present and declares nothing.

    A file that is named but cannot be read is a warning naming the path and the error
    class — never a value — and an empty mapping: the caller sees "declares nothing" and
    refuses for that reason instead, which reads the same to an operator and needs no
    third state.
    """
    path = _resolve(config, config_path)
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        logger.warning(
            "env file %s cannot be read (%s); it declares nothing for this run",
            path,
            type(exc).__name__,
        )
        return ({}, ())
    parsed = envfile.parse(text)
    if parsed.invalid_lines:
        logger.warning(
            "env file %s: skipped malformed %s",
            path,
            ", ".join(f"line {n}" for n in parsed.invalid_lines),
        )
    return (dict(parsed.values), parsed.invalid_lines)


def _resolve(config: Mapping, config_path: Path) -> Optional[Path]:
    """``env.file`` resolved exactly as the loader resolves it, or ``None``."""
    from .cli_config import resolve_env_file

    try:
        return resolve_env_file(config, config_path)
    except Exception:  # noqa: BLE001 — a broken config block names no file
        logger.warning("could not resolve env.file; treating it as unset")
        return None


def process_environ(pid: int) -> Optional[Dict[str, str]]:
    """``pid``'s own environment, or ``None`` when this host will not say.

    ``/proc/<pid>/environ`` where it exists; ``ps eww`` where it does not (macOS and the
    BSDs print a process's environment there for its own user). Every failure — the
    process has exited, the read is denied, neither mechanism is present, the output is
    not parseable — is ``None``. Callers report that as *unverified*: the absence of an
    answer, never an answer of its own.

    Both sources report the environment a process was **started with**, not one it has
    ``setenv``-ed since. That is the right question and not a limitation: a harness reads
    its credentials once, at startup, which is the whole of why a rotation never reaches
    a session that was already running.
    """
    if pid <= 0:
        return None
    from_proc = _read_proc(pid)
    if from_proc is not None:
        return from_proc
    return _read_ps(pid)


def _read_proc(pid: int) -> Optional[Dict[str, str]]:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except (OSError, ValueError):
        return None
    return _parse_nul_separated(raw.decode("utf-8", "surrogateescape"))


def _read_ps(pid: int) -> Optional[Dict[str, str]]:
    """The ``ps eww`` fallback. Best effort by construction, and it says so.

    ``ps`` prints ``pid tty stat time command NAME=value NAME=value …`` on one line, so
    a value containing a space is indistinguishable from the start of the next variable.
    That is tolerable here because the comparison is by name: a name whose value this
    mangles reads as *differing*, which errs toward telling the operator to look — never
    toward silence.
    """
    try:
        proc = subprocess.run(
            ["ps", "eww", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=_PS_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    found: Dict[str, str] = {}
    for token in lines[1].split(" "):
        name, sep, value = token.partition("=")
        if sep and envfile.NAME_RE.fullmatch(name):
            found[name] = value
    return found or None


def _parse_nul_separated(text: str) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for entry in text.split("\0"):
        name, sep, value = entry.partition("=")
        if sep and name:
            found[name] = value
    return found


def compare(
    declared_values: Mapping[str, str], actual: Mapping[str, str]
) -> Tuple[str, ...]:
    """The declared names ``actual`` does not match, in name order.

    A name the process does not carry at all counts as differing: an unset credential is
    as broken as a retired one, and both are fixed by the same relaunch. Names ``actual``
    carries that the file does not declare are not compared — the file is the statement
    of what the-loop manages, and the rest of a process's environment is not its business.
    """
    return tuple(
        name
        for name in sorted(declared_values)
        if actual.get(name) != declared_values[name]
    )


def environ_matches_declared(
    declared_values: Mapping[str, str], pid: int
) -> Tuple[str, Tuple[str, ...]]:
    """``("fresh"|"stale"|"unverified", differing names)`` for one process."""
    actual = process_environ(pid)
    if actual is None:
        return ("unverified", ())
    differing = compare(declared_values, actual)
    return ("stale" if differing else "fresh", differing)


def spawn_environment(config_getter) -> Dict[str, str]:
    """The names and values a pane spawned **now** should carry; ``{}`` when none.

    Handed to :class:`~the_loop.runner.TmuxRunner` as its ``env_provider`` so that every
    spawn re-reads the file rather than inheriting the tmux server's environment — which
    is the copy that was frozen when the server started and is never refreshed again.

    ``config_getter`` returns the operator's CLI config; the path is resolved the way
    every other reader resolves it. Never raises: a spawn must not fail because an env
    file moved.
    """
    from .cli_config import default_cli_config_path

    try:
        config = config_getter() or {}
        result = declared(config, default_cli_config_path())
    except Exception:  # noqa: BLE001 — a spawn never fails on the env file
        logger.warning("could not read the env file for this spawn; carrying none")
        return {}
    if result is None:
        return {}
    return dict(result[0])
