"""Per-work-item pause ledger — "leave this one alone for now" (issue-98).

Before this module the only lever over a work item was ``sessions close``, which
*ends* its session (and, since issue-94, the harness conversation inside it).
A pause is the softer one the operator actually reaches for: the-loop stops
acting on a work item — no spawn, no comment forwarding, no event delivery —
while its session, its tmux transcript and its checkout stay exactly as they
are. Resuming picks the item back up.

Written by ``the-loop sessions pause`` and read by both ingress paths — the
webhook dispatcher and the poller — so one lever covers them both.

The ledger is ONE JSON file (default ``.the-loop/state/paused.json``), unlike the
file-per-session registry: a pause is a tiny record, the whole set is read every
poll cycle, and writes come from human-driven CLI invocations rather than from
racing daemons. Writes are atomic (tempfile + ``os.replace``); the daemon
re-reads the file when its ``(mtime, size)`` changes, so a pause typed in
another terminal takes effect on the next cycle with no restart.

Fails **safe, not paused**: a missing file means nothing is paused, and an
unreadable or corrupt one warns once and is treated as empty. A broken ledger
must never wedge the daemon, and must never silently pause everything.

Spec: docs/specs/issue-98/design.md §2.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Union

from ..state import STATE_DIR
from .registry import WorkItemRef

logger = logging.getLogger("the-loop.sessions")

# What wrote a pause record — rendered by `sessions show`. Only the CLI writes
# one today; the value is recorded so a future control (e.g. a GitHub label,
# deferred out of issue-98) is distinguishable without a migration.
SOURCE_LOCAL = "local"

DEFAULT_PAUSE_FILE = f"{STATE_DIR}/paused.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_ref(work_item: Union[str, WorkItemRef]) -> str:
    if isinstance(work_item, WorkItemRef):
        return work_item.ref
    return str(work_item)


@dataclass(frozen=True)
class PauseRecord:
    """One paused work item: its ref, why, since when, and who paused it."""

    ref: str
    reason: str = ""
    paused_at: str = ""
    source: str = SOURCE_LOCAL  # what wrote it; only the CLI does today

    def to_dict(self) -> dict:
        return {
            "ref": self.ref,
            "reason": self.reason,
            "pausedAt": self.paused_at,
            "source": self.source,
        }


@dataclass(frozen=True)
class PauseState:
    """Whether a work item is paused, and what put it on hold."""

    paused: bool = False
    record: Optional[PauseRecord] = None

    @property
    def sources(self) -> List[str]:
        return [self.record.source] if self.record else []

    @property
    def reason(self) -> str:
        return self.record.reason if self.record else ""


class PauseStore:
    """The pause ledger. Never raises on a bad file; see the module docstring."""

    def __init__(self, path: Union[str, Path] = DEFAULT_PAUSE_FILE):
        self.path = Path(path)
        self._records: dict = {}
        self._stamp: Optional[tuple] = None
        self._warned = False
        self._load()

    # -- storage ---------------------------------------------------------------

    def _current_stamp(self) -> Optional[tuple]:
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def _load(self) -> None:
        stamp = self._current_stamp()
        self._stamp = stamp
        if stamp is None:
            self._records = {}
            return
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError) as exc:
            if not self._warned:
                self._warned = True
                logger.warning(
                    "ignoring unreadable pause ledger %s (%s); treating nothing as "
                    "paused",
                    self.path,
                    exc,
                )
            self._records = {}
            return
        self._warned = False
        paused = (data or {}).get("paused")
        self._records = dict(paused) if isinstance(paused, dict) else {}

    def _refresh(self) -> None:
        """Re-read when the file changed underneath us (CLI writes, daemon reads)."""
        if self._current_stamp() != self._stamp:
            self._load()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump({"paused": self._records}, handle, indent=2)
                handle.write("\n")
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise
        self._stamp = self._current_stamp()

    # -- queries ---------------------------------------------------------------

    def record(self, work_item: Union[str, WorkItemRef]) -> Optional[PauseRecord]:
        """The local pause record for ``work_item``, or ``None``."""
        self._refresh()
        raw = self._records.get(_as_ref(work_item))
        if not isinstance(raw, dict):
            return None
        return PauseRecord(
            ref=_as_ref(work_item),
            reason=str(raw.get("reason") or ""),
            paused_at=str(raw.get("pausedAt") or ""),
            source=str(raw.get("source") or SOURCE_LOCAL),
        )

    def is_paused(self, work_item: Union[str, WorkItemRef]) -> bool:
        """True when a pause record exists for this work item."""
        return self.record(work_item) is not None

    def state(self, work_item: Union[str, WorkItemRef]) -> PauseState:
        """The gate both ingress paths call."""
        record = self.record(work_item)
        return PauseState(paused=record is not None, record=record)

    def list_paused(self) -> List[PauseRecord]:
        self._refresh()
        return [
            PauseRecord(
                ref=ref,
                reason=str((raw or {}).get("reason") or ""),
                paused_at=str((raw or {}).get("pausedAt") or ""),
                source=str((raw or {}).get("source") or SOURCE_LOCAL),
            )
            for ref, raw in sorted(self._records.items())
            if isinstance(raw, dict)
        ]

    # -- mutations -------------------------------------------------------------

    def pause(
        self,
        work_item: Union[str, WorkItemRef],
        reason: str = "",
        source: str = SOURCE_LOCAL,
    ) -> bool:
        """Pause ``work_item``. False when it was already paused (idempotent)."""
        self._refresh()
        ref = _as_ref(work_item)
        if ref in self._records:
            return False
        self._records[ref] = {
            "reason": reason,
            "pausedAt": _utcnow(),
            "source": source,
        }
        self._save()
        logger.info("paused %s%s", ref, f" ({reason})" if reason else "")
        return True

    def resume(self, work_item: Union[str, WorkItemRef]) -> bool:
        """Clear the pause. False when it was not paused (idempotent)."""
        self._refresh()
        ref = _as_ref(work_item)
        if ref not in self._records:
            return False
        self._records.pop(ref, None)
        self._save()
        logger.info("resumed %s", ref)
        return True
