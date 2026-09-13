"""Availability: which models and effort levels a harness on THIS machine accepts.

Issue-358, requirement 7. The mechanism that answers *"what if the harness does not have
that model?"* — **do not offer it, and never spawn on it.**

It is the reason :mod:`the_loop.modelchoice` can keep ``models`` a plain list of names
with no harness attached: the model×harness relation is **measured** rather than declared.
The probe asks each harness whether it can actually run a name, caches the answer, and the
gate offers only what came back ``ok`` or ``unknown``. A declaration may *narrow* which
combinations get asked about; only a verdict may confirm one.

Separate from :mod:`the_loop.modelchoice` because this is the only part that **runs a
process**. Keeping the pure resolution rules out of reach of a subprocess call is what
lets every one of them be unit-tested with no harness installed.

Three properties worth stating, because they are the guard rather than decoration:

* **The prompt is a the-loop constant.** No text from a work item is ever sent to a
  vendor by this module — the probe carries :data:`PROBE_PROMPT` and the resolved
  arguments, nothing else.
* **It never runs on the delivery path.** Probing happens in ``the-loop models check``, at
  daemon start, and on the one stale-verdict re-probe; a dispatch reads the cache.
* **The cache may withhold, never introduce.** Resolution is always against what the
  operator declared, so a hand-edited verdict for an undeclared model buys nothing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .modelchoice import effort_args as _effort_args
from .modelchoice import model_args as _model_args

logger = logging.getLogger("the-loop.modelprobe")

__all__ = [
    "OK",
    "PROBE_PROMPT",
    "PROBE_TIMEOUT_SECONDS",
    "REFUSED",
    "UNKNOWN",
    "VERDICT_TTL_SECONDS",
    "Verdict",
    "VerdictCache",
    "offerable",
    "probe",
    "resolved_args",
]

#: The three verdicts. ``unknown`` is deliberately **not** a failure: a machine with no
#: harness binary, or no network at probe time, must not lose a capability the operator
#: declared (R7.6), so an unprobed choice stays offerable.
OK = "ok"
REFUSED = "refused"
UNKNOWN = "unknown"

#: What the probe asks. A fixed the-loop constant — never any text from a work item, a
#: comment or a repository. The cheapest thing that still proves the harness accepted the
#: arguments: if the model or the flag is wrong, the CLI fails before answering.
PROBE_PROMPT = "the-loop availability probe: reply with the single word ok"

#: A probe that has not answered in this long is ``unknown``, not ``refused``.
PROBE_TIMEOUT_SECONDS = 60.0

#: How long a verdict stands before it is asked again. A model is withdrawn or granted on
#: a vendor's schedule, not ours, so the answer is re-checked daily rather than cached for
#: the life of a daemon.
VERDICT_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class Verdict:
    """One answer: can ``harness`` run ``name``?

    ``args_digest`` records **what was actually probed**, so a changed adapter mapping or
    a changed flag invalidates the answer rather than silently standing for argv nobody
    tested.
    """

    harness: str
    kind: str  # "model" | "effort"
    name: str
    args_digest: str
    verdict: str
    checked_at: float

    def to_dict(self) -> dict:
        return {
            "harness": self.harness,
            "kind": self.kind,
            "name": self.name,
            "argsDigest": self.args_digest,
            "verdict": self.verdict,
            "checkedAt": self.checked_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Verdict":
        return cls(
            harness=str(data["harness"]),
            kind=str(data["kind"]),
            name=str(data["name"]),
            args_digest=str(data.get("argsDigest") or ""),
            verdict=str(data.get("verdict") or UNKNOWN),
            checked_at=float(data.get("checkedAt") or 0.0),
        )

    @property
    def key(self) -> Tuple[str, str, str]:
        return (self.harness, self.kind, self.name)


def digest(args: Sequence[str]) -> str:
    """A stable fingerprint of the argv a verdict was taken against."""
    return hashlib.sha256("\x00".join(str(a) for a in args).encode()).hexdigest()[:16]


def resolved_args(kind: str, name: str, adapter: Any) -> Tuple[str, ...]:
    """The argv fragment ``name`` resolves to on ``adapter`` — ``()`` when it cannot."""
    if kind == "model":
        return _model_args(name, adapter)
    if kind == "effort":
        return _effort_args(name, adapter)
    return ()


def _run(argv: Sequence[str], adapter: Any, timeout: float) -> Tuple[int, str]:
    """Run the harness once. Split out so tests decide the outcome, not a binary."""
    proc = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def probe(
    kind: str, name: str, adapter: Any, timeout: float = PROBE_TIMEOUT_SECONDS
) -> Verdict:
    """Ask ``adapter``'s harness whether it can run ``name``.

    A non-zero exit is ``refused`` — the harness itself said no. A run that could not
    start at all (no binary, a timeout, an OS error) is ``unknown``, because that is a
    fact about this machine rather than about the name.

    A choice that resolves to **no arguments** is ``refused`` without running anything:
    there is nothing to ask, and nothing to offer. That is the honest answer for an effort
    level a harness cannot express — never a silent "ran without it".
    """
    args = resolved_args(kind, name, adapter)
    harness = str(getattr(adapter, "name", "") or "")
    if not args:
        return Verdict(harness, kind, name, "", REFUSED, time.time())
    argv = [adapter.binary] + list(adapter.oneshot_argv(PROBE_PROMPT)) + list(args)
    try:
        code, output = _run(argv, adapter, timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.info("could not probe %s %r on %s: %s", kind, name, harness, exc)
        return Verdict(harness, kind, name, digest(args), UNKNOWN, time.time())
    if code != 0:
        logger.info(
            "%s refused %s %r (exit %s): %s",
            harness,
            kind,
            name,
            code,
            " ".join(output.split())[:200],
        )
        return Verdict(harness, kind, name, digest(args), REFUSED, time.time())
    return Verdict(harness, kind, name, digest(args), OK, time.time())


class VerdictCache:
    """The probed matrix, on disk, machine-local.

    Every read is best-effort: an unreadable or hand-mangled file is an **empty** cache,
    which means "nothing probed" — offerable, never refused. A fault here must not silently
    withdraw the operator's declared capabilities.
    """

    def __init__(self, path: str):
        self.path = path
        self._entries: Optional[Dict[Tuple[str, str, str], Verdict]] = None

    def _load(self) -> Dict[Tuple[str, str, str], Verdict]:
        if self._entries is not None:
            return self._entries
        entries: Dict[Tuple[str, str, str], Verdict] = {}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            data = {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("could not read the verdict cache %s: %s", self.path, exc)
            data = {}
        for raw in (data or {}).get("verdicts") or []:
            try:
                verdict = Verdict.from_dict(raw)
            except (KeyError, TypeError, ValueError) as exc:
                logger.debug("skipping an unreadable verdict: %s", exc)
                continue
            entries[verdict.key] = verdict
        self._entries = entries
        return entries

    def get(
        self, harness: str, kind: str, name: str, args_digest: str = ""
    ) -> Optional[Verdict]:
        """The standing verdict, or ``None`` when there is none that still applies.

        ``None`` for an entry that has expired or that was taken against different
        argv — both mean "ask again", which is the safe direction: a stale answer is
        never allowed to withhold a choice forever.
        """
        verdict = self._load().get((harness, kind, name))
        if verdict is None:
            return None
        if time.time() - verdict.checked_at > VERDICT_TTL_SECONDS:
            return None
        if args_digest and verdict.args_digest and verdict.args_digest != args_digest:
            return None
        return verdict

    def put(self, verdict: Verdict) -> None:
        entries = self._load()
        entries[verdict.key] = verdict
        self._write(entries)

    def put_all(self, verdicts: Sequence[Verdict]) -> None:
        entries = self._load()
        for verdict in verdicts:
            entries[verdict.key] = verdict
        self._write(entries)

    def all(self) -> List[Verdict]:
        return list(self._load().values())

    def _write(self, entries: Dict[Tuple[str, str, str], Verdict]) -> None:
        payload = {"verdicts": [v.to_dict() for v in entries.values()]}
        directory = os.path.dirname(self.path) or "."
        try:
            os.makedirs(directory, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                "w", dir=directory, delete=False, encoding="utf-8"
            )
            with handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
            os.replace(handle.name, self.path)
        except OSError as exc:  # never fail a caller over telemetry-shaped state
            logger.warning("could not write the verdict cache %s: %s", self.path, exc)


def offerable(
    kind: str, name: str, harness: str, cache: VerdictCache, args_digest: str = ""
) -> bool:
    """Whether ``name`` may be offered for ``harness``.

    ``ok`` and *unprobed* are offerable; only a standing ``refused`` withholds. That
    asymmetry is R7.6: the probe exists to stop a work item dying on a model the harness
    rejects, not to make an unprobeable machine useless.
    """
    verdict = cache.get(harness, kind, name, args_digest=args_digest)
    return verdict is None or verdict.verdict != REFUSED
