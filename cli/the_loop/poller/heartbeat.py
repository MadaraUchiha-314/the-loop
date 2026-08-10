"""The poller's heartbeat — what ``the-loop poll status`` reports beyond liveness
(issue-191).

"Is the poller running?" is answered by the flock on its pidfile, and only by
that (:mod:`the_loop.runlock`). This file answers the *next* question — is it
making progress? — with three facts a lock cannot carry: when this poller
started, when it last completed a cycle, and what that cycle did. Together they
turn a ``ps``/pidfile/log cross-check into one command.

**Never the source of truth for liveness.** A heartbeat is a claim written by a
process that may since have died, and anyone who can write ``state.root`` can
forge one. ``poll status`` therefore takes liveness from the lock and treats this
file as enrichment: a recent ``lastCycleAt`` beside a lock nobody holds means the
poller *stopped* after that cycle, which is exactly what it says.

It is deliberately **not** removed when the poller stops, so ``poll status`` can
still say when the last cycle ran, and it is rewritten atomically (``tempfile`` +
``os.replace``) like the record stores, so a crash never leaves half a file. A
write that fails warns once and is swallowed: observability must never break
ingress.

Spec: docs/specs/issue-191/design.md.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger("the-loop.poll")

__all__ = ["Heartbeat", "PollHeartbeat"]


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Heartbeat:
    """One reading of ``<state.root>/poll-status.json``."""

    pid: int = 0
    started_at: str = ""
    last_cycle_at: str = ""
    interval_seconds: int = 0
    last_cycle: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict) -> "Heartbeat":
        return cls(
            pid=int(data.get("pid") or 0),
            started_at=str(data.get("startedAt") or ""),
            last_cycle_at=str(data.get("lastCycleAt") or ""),
            interval_seconds=int(data.get("intervalSeconds") or 0),
            last_cycle=dict(data.get("lastCycle") or {}),
        )

    def to_mapping(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "startedAt": self.started_at,
            "lastCycleAt": self.last_cycle_at,
            "intervalSeconds": self.interval_seconds,
            "lastCycle": dict(self.last_cycle),
        }


class PollHeartbeat:
    """Writes the heartbeat after every cycle; reads it for ``poll status``."""

    def __init__(
        self,
        path: Union[str, os.PathLike],
        pid: Optional[int] = None,
        interval_seconds: int = 0,
        started_at: str = "",
    ):
        self.path = Path(path)
        self.pid = os.getpid() if pid is None else int(pid)
        self.interval_seconds = int(interval_seconds)
        self.started_at = started_at or _utcnow()
        self._warned = False

    # -- writing ----------------------------------------------------------------

    def record(
        self, summary: Any = None, interval_seconds: Optional[int] = None
    ) -> None:
        """Write this poller's state after a completed cycle.

        ``summary`` is a :class:`~the_loop.poller.poller.PollSummary`; it is read
        duck-typed rather than imported, so the writer does not depend on the
        poller module it is called from. ``None`` records a started-but-not-yet-
        cycled poller.
        """
        if interval_seconds is not None:
            self.interval_seconds = int(interval_seconds)
        beat = Heartbeat(
            pid=self.pid,
            started_at=self.started_at,
            last_cycle_at=_utcnow() if summary is not None else "",
            interval_seconds=self.interval_seconds,
            last_cycle=_counters(summary),
        )
        self._write(beat)

    def _write(self, beat: Heartbeat) -> None:
        payload = json.dumps(beat.to_mapping(), indent=2) + "\n"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=str(self.path.parent),
                prefix=self.path.name + ".",
                suffix=".tmp",
                delete=False,
            )
            try:
                with handle:
                    handle.write(payload)
                os.replace(handle.name, self.path)
            except BaseException:
                _unlink(handle.name)
                raise
        except OSError as exc:
            if not self._warned:  # warn once — never break ingress over o11y
                self._warned = True
                logger.warning("cannot write the poll heartbeat %s: %s", self.path, exc)

    # -- reading ----------------------------------------------------------------

    @staticmethod
    def read(path: Union[str, os.PathLike]) -> Optional[Heartbeat]:
        """The recorded heartbeat, or ``None`` when it is absent or unreadable.

        ``None`` is the honest answer for a poller started before this file
        existed, or one whose heartbeat has been deleted — ``poll status`` still
        reports liveness and pid from the lock in both cases.
        """
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        return Heartbeat.from_mapping(data)


def _counters(summary: Any) -> Dict[str, Any]:
    """A ``PollSummary``'s counters as JSON, or ``{}`` when there was no cycle."""
    if summary is None:
        return {}
    return {
        "itemsSeen": int(getattr(summary, "items_seen", 0)),
        "spawns": int(getattr(summary, "spawns", 0)),
        "commentsForwarded": int(getattr(summary, "comments_forwarded", 0)),
        "closures": int(getattr(summary, "closures", 0)),
        "failures": int(getattr(summary, "failures", 0)),
        "errors": len(getattr(summary, "errors", ()) or ()),
        "interrupted": bool(getattr(summary, "interrupted", False)),
    }


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:  # pragma: no cover - the replace already consumed it
        pass
