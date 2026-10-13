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

Since issue-482 the file is **not** what a session is handed. ``env.file`` holds the
daemon's credentials, and the-loop never sends a secret to an agent session: a pane gets
the-loop's own identifiers plus the names the operator lists in ``env.sessionPassthrough``
(never a credential), and every other declared or credential name is removed from it.
:class:`SessionEnvironment` is that boundary, and :func:`compare` checks a running pane
against it.

Spec: docs/specs/issue-410/design.md, docs/specs/issue-482/design.md.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, Mapping, Optional, Tuple, Union

from . import envfile

logger = logging.getLogger("the-loop.envstate")

__all__ = [
    "FINGERPRINT_LENGTH",
    "SessionEnvironment",
    "compare",
    "credential_names",
    "declared",
    "environ_matches_declared",
    "fingerprint",
    "passthrough_names",
    "process_environ",
    "session_environment",
    "session_environment_and_lines",
    "spawn_environment",
]

#: How much of the digest is shown. Long enough that two live credentials will not
#: collide, short enough to read at a glance in a table — and a one-way function of a
#: high-entropy secret either way, which is what makes printing it safe at all.
FINGERPRINT_LENGTH = 8

#: How long ``ps`` gets to answer. It is a fallback on a platform without ``/proc``;
#: a hung ``ps`` must degrade to "unverified", never hold up a restart.
_PS_TIMEOUT_SECONDS = 10

#: A config key that names a credential's variable (issue-482, R4.2):
#: ``tokenEnv``, ``botTokenEnv``, ``secretEnv``… A pattern, not a list of paths, so a
#: credential key added later is covered without touching this module.
_CREDENTIAL_KEY_RE = re.compile(r"(token|secret)Env$", re.IGNORECASE)

#: The variables a credential is read from when the config names none: GitHub's
#: (``ghapi.DEFAULT_TOKEN_ENVS``) and the schema defaults of the Slack and webhook keys.
_DEFAULT_CREDENTIAL_NAMES: FrozenSet[str] = frozenset(
    {
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "THE_LOOP_GH_WEBHOOK_SECRET",
        "THE_LOOP_SLACK_BOT_TOKEN",
        "THE_LOOP_SLACK_APP_TOKEN",
    }
)

#: the-loop's own identifiers a pane is always given (issue-322, issue-370, issue-393).
#: Never removed, whatever the env file says: the runner sets them last.
_OWN_NAMES: FrozenSet[str] = frozenset(
    {"THE_LOOP_INSTANCE", "THE_LOOP_WORK_ITEM", "THE_LOOP_CLI_CONFIG"}
)


@dataclass(frozen=True)
class SessionEnvironment:
    """What a spawned pane is given, and what it must not hold (issue-482).

    ``forward`` is the operator's non-secret passthrough, with values. ``remove`` is
    every name ``env.file`` declares and every credential name, minus ``forward``: the
    runner strips them from the pane whatever the tmux server holds.
    """

    forward: Dict[str, str] = field(default_factory=dict)
    remove: Tuple[str, ...] = ()


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


Wanted = Union[SessionEnvironment, Mapping[str, str]]


def _as_session_environment(wanted: Wanted) -> SessionEnvironment:
    if isinstance(wanted, SessionEnvironment):
        return wanted
    return SessionEnvironment(forward=dict(wanted))


def compare(wanted: Wanted, actual: Mapping[str, str]) -> Tuple[str, ...]:
    """The names where ``actual`` is not what a session should hold, in name order.

    A forwarded name the process does not carry, or carries with another value, differs:
    an unset variable is as broken as a retired one, and both are fixed by the same
    relaunch. A removed name differs when the process carries it **at all** (issue-482):
    a session holding a credential is the defect, whatever its value. Anything else
    ``actual`` carries is not the-loop's business. A plain mapping is read as
    ``forward``.
    """
    env = _as_session_environment(wanted)
    differing = {
        name for name, value in env.forward.items() if actual.get(name) != value
    }
    differing.update(name for name in env.remove if name in actual)
    return tuple(sorted(differing))


def environ_matches_declared(
    declared_values: Wanted, pid: int
) -> Tuple[str, Tuple[str, ...]]:
    """``("fresh"|"stale"|"unverified", differing names)`` for one process."""
    actual = process_environ(pid)
    if actual is None:
        return ("unverified", ())
    differing = compare(declared_values, actual)
    return ("stale" if differing else "fresh", differing)


def credential_names(config: Mapping) -> FrozenSet[str]:
    """Every variable the config reads a credential from, plus the defaults (R4.2).

    A walk of the whole config: a string, or each string in a list, under any key that
    ends in ``tokenEnv``/``secretEnv`` (any case). A session must never hold one, and the
    passthrough refuses one, so the set errs toward too many names, never too few.
    """
    found = set(_DEFAULT_CREDENTIAL_NAMES)

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if isinstance(key, str) and _CREDENTIAL_KEY_RE.search(key):
                    values = value if isinstance(value, (list, tuple)) else [value]
                    # A name only: anything else could never be a variable, and
                    # reaching `env -u` it would fail the spawn.
                    found.update(
                        v
                        for v in values
                        if isinstance(v, str) and envfile.NAME_RE.fullmatch(v)
                    )
                else:
                    walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(config)
    return frozenset(found)


def passthrough_names(config: Mapping) -> Tuple[str, ...]:
    """``env.sessionPassthrough``: the non-secret names a pane may be given (R4).

    A credential name is dropped with a warning naming the variable, never its value
    (R4.3), and so is anything that is not a variable name. Order and first occurrence
    are kept.
    """
    block = config.get("env") if isinstance(config, Mapping) else None
    listed = block.get("sessionPassthrough") if isinstance(block, Mapping) else None
    if not isinstance(listed, (list, tuple)):
        return ()
    secrets = credential_names(config)
    kept: list = []
    for name in listed:
        if not isinstance(name, str) or not envfile.NAME_RE.fullmatch(name):
            logger.warning("env.sessionPassthrough: %r is not a variable name", name)
        elif name in secrets:
            logger.warning(
                "env.sessionPassthrough: %s names a credential; a session is never "
                "given one, so it is not forwarded",
                name,
            )
        elif name not in kept:
            kept.append(name)
    return tuple(kept)


def session_environment(
    config: Mapping, config_path: Path
) -> Optional[SessionEnvironment]:
    """The boundary for a pane spawned **now**, or ``None`` when nothing is configured.

    ``None`` means neither ``env.file`` nor ``env.sessionPassthrough`` is set — the
    state ``status`` reports as "not configured" and ``sessions restart`` refuses on.
    Otherwise ``forward`` takes each passthrough name from the file when it declares
    it (re-read now: issue-410's rotation rule), else from this process's environment,
    else skips it (R4.4); and ``remove`` is every other name the file declares plus
    every credential name. An unreadable file still removes the credential names: they
    come from the config, not the file.
    """
    result = session_environment_and_lines(config, config_path)
    return None if result is None else result[0]


def session_environment_and_lines(
    config: Mapping, config_path: Path
) -> Optional[Tuple[SessionEnvironment, Tuple[int, ...]]]:
    """:func:`session_environment`, plus the env file's malformed line numbers."""
    passthrough = passthrough_names(config)
    result = declared(config, config_path)
    if result is None and not passthrough:
        return None
    file_values, invalid_lines = result if result is not None else ({}, ())
    forward: Dict[str, str] = {}
    for name in passthrough:
        if name in file_values:
            forward[name] = file_values[name]
        elif name in os.environ:
            forward[name] = os.environ[name]
    remove = (set(file_values) | credential_names(config)) - set(forward) - _OWN_NAMES
    return (
        SessionEnvironment(forward=forward, remove=tuple(sorted(remove))),
        invalid_lines,
    )


def spawn_environment(config_getter) -> SessionEnvironment:
    """The boundary a pane spawned **now** is given; the runner's ``env_provider``.

    Every spawn re-reads the file (issue-410), so a rotated passthrough value reaches
    the next pane. With nothing configured it still removes the credential names: a
    tmux server the daemon started inherited the daemon's environment, and a pane must
    not inherit a token from it (issue-482, R1.4).

    ``config_getter`` returns the operator's CLI config; the path is resolved the way
    every other reader resolves it. Never raises: a spawn must not fail because an env
    file moved — and the fallback still strips the default credential names.
    """
    from .cli_config import default_cli_config_path

    config: Mapping = {}
    try:
        config = config_getter() or {}
        env = session_environment(config, default_cli_config_path())
    except Exception:  # noqa: BLE001 — a spawn never fails on the env file
        logger.warning("could not read the env file for this spawn; forwarding none")
        env = None
    if env is not None:
        return env
    try:
        names = credential_names(config)
    except Exception:  # noqa: BLE001 — a malformed config still strips the defaults
        names = _DEFAULT_CREDENTIAL_NAMES
    return SessionEnvironment(remove=tuple(sorted(names - _OWN_NAMES)))
