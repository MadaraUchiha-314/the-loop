"""Work-item state — a cache, never an authority.

``docs/specs/<id>/work-item-state.json`` records where a work item is. It is
checked in, so it survives a machine change, a session change and a multi-day
human review, and it is reviewable in a PR diff.

It was ``graph-state.json`` until issue-365. The name was too narrow for what the
file had become: the pointer and the node records are the graph's, but the
surface, the session, the PR-session mode, the model, the effort and (since the
same issue) the repositories this work item contributes to are facts about the
**work item**, true whichever loop it walks.

But it is explicitly **not** the source of truth (issue-109, R8.4): the agent can
write this file, and the agent is the subject of the gates it records. So
``reconstruct()`` re-derives the current node from the artifacts alone, and the
repository-boundary check always uses it. An agent editing its own scorecard
cannot thereby pass a gate.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger("the-loop.graph")

__all__ = [
    "LEGACY_STATE_FILENAME",
    "STATE_FILENAME",
    "StateLockBusy",
    "WorkItemState",
    "state_lock",
    "utc_now",
]

STATE_FILENAME = "work-item-state.json"
LOCK_FILENAME = "work-item-state.lock"

#: What the file was called until issue-365. **Read** when the current name is
#: absent, and never written: a work item already in flight keeps its pointer
#: across the upgrade with no migration step, and its next save writes the
#: current name beside the old one. Readers that glob for inner-loop states
#: accept both for the same reason.
LEGACY_STATE_FILENAME = "graph-state.json"

STATE_VERSION = 1


class StateLockBusy(RuntimeError):
    """Another writer holds the work-item-state lock (issue-148)."""


@contextlib.contextmanager
def state_lock(spec_dir: Path, timeout: float = 2.0) -> Iterator[None]:
    """Advisory lock serialising state writers (issue-148, D-concurrency).

    `work-item-state.json` has two writers now — the daemon's GraphLink and the
    session's `the-loop graph complete` — so the load→mutate→save window is
    held under an `fcntl.flock` on a sibling lock file. Stdlib only; where
    `fcntl` does not exist (non-POSIX) this degrades to no locking, which is
    acceptable because claims are idempotent and evaluation re-derives from
    artifacts: a lost update costs a re-run, never a wrong pointer.

    Raises :class:`StateLockBusy` when the lock cannot be taken within
    ``timeout`` — callers report "busy" rather than blocking a poll cycle.
    """
    try:
        import fcntl
    except ImportError:  # non-POSIX: documented no-op fallback
        yield
        return
    spec_dir.mkdir(parents=True, exist_ok=True)
    with open(spec_dir / LOCK_FILENAME, "w", encoding="utf-8") as fh:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise StateLockBusy(
                        f"could not lock {spec_dir / LOCK_FILENAME} within {timeout}s"
                    ) from None
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _string_list(raw: Any) -> List[str]:
    """Non-empty strings from a list, or ``[]`` for anything that is not one."""
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(entry).strip() for entry in raw if str(entry).strip()]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class NodeRecord:
    attempts: int = 0
    outcome: str = ""
    entered_at: str = ""
    exited_at: str = ""
    last_block: str = ""
    forced: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "attempts": self.attempts,
            "outcome": self.outcome,
            "enteredAt": self.entered_at,
            "exitedAt": self.exited_at,
            "lastBlock": self.last_block,
            "forced": self.forced,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeRecord":
        return cls(
            attempts=int(data.get("attempts", 0)),
            outcome=str(data.get("outcome", "")),
            entered_at=str(data.get("enteredAt", "")),
            exited_at=str(data.get("exitedAt", "")),
            last_block=str(data.get("lastBlock", "")),
            forced=bool(data.get("forced", False)),
        )


@dataclass
class WorkItemState:
    work_item: str
    current_node: str = ""
    nodes: Dict[str, NodeRecord] = field(default_factory=dict)
    decisions: Dict[str, Any] = field(default_factory=dict)
    forced: List[Dict[str, Any]] = field(default_factory=list)
    parked: Optional[Dict[str, Any]] = None
    session: Optional[Dict[str, Any]] = None
    completions: Dict[str, Any] = field(default_factory=dict)
    #: Declared skips (issue-177): node id -> {via, token, by, reason, at}.
    #: A DECLARATION with provenance, never a verdict — the runtime honours an
    #: entry only when the compiled graph marks that node skippable, so a
    #: hand-written entry on a protected node is inert. Additive: absent in
    #: every pre-issue-177 state file, defaulting to {} on load.
    skips: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    #: Selected opt-in phases (issue-188): node id -> {via, by, at}. The mirror
    #: of ``skips`` — a node the compiled graph marks ``optIn`` does NOT run
    #: until an authorized human ticks it at `phase-selection`, and this is
    #: where that choice is recorded with provenance. Filtered through the
    #: compiled graph on every read, exactly as ``skips`` is, so a hand-written
    #: entry on a node that is not opt-in is inert. Additive: absent in every
    #: pre-issue-188 state file, defaulting to {} — which reads correctly as
    #: "this work item was never offered the choice".
    opt_ins: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    #: The outer loop's collaboration surface for this work item (issue-183):
    #: ``pull-request`` when its author ticked that box at `phase-selection`,
    #: ``""`` otherwise — which reads as the default, the work item itself.
    #: Frozen by the same signed reply that freezes the phase selection, so it
    #: is a recorded fact rather than a live comment. Additive: absent in every
    #: pre-issue-183 state file.
    surface: str = ""
    #: The CONTRIBUTING repositories this work item raises pull requests in
    #: (issue-183), ticked by an authorized human at `phase-selection` and frozen
    #: by the same signed reply as every other per-work-item choice (issue-365,
    #: decision-127). `await-inner-loops` holds `implementation` until each of
    #: them has an inner loop AND every started loop has finished. An empty list
    #: is **no declaration**, never an empty one — the gate then behaves exactly
    #: as it did before the key existed. It lived in an artifact's front matter
    #: until issue-365; an artifact is editable by anyone who can edit the file,
    #: and this input decides which repositories an unattended agent opens pull
    #: requests in.
    repos: List[str] = field(default_factory=list)
    #: Which shipped loop this state walks (issue-185): recorded once by
    #: ``Runtime.start`` from the compiled graph's own name, so a contribution
    #: item is addressed by the right graph on every later read. Additive:
    #: absent in every pre-issue-185 state file, and an empty value reads as
    #: the shipped default for this state location. Agent-writable like the
    #: whole file, so readers accept only shipped loop names (fail closed to
    #: the default) — see ``model.SHIPPED_LOOPS``.
    loop: str = ""
    version: int = STATE_VERSION

    # -- persistence ----------------------------------------------------------

    @staticmethod
    def path_for(spec_dir: Path) -> Path:
        return spec_dir / STATE_FILENAME

    @staticmethod
    def existing_path(spec_dir: Path) -> Optional[Path]:
        """The state file to READ: the current name, else the pre-issue-365 one.

        Present-name-wins is the whole rule. A work item that has saved since the
        rename has both files only if somebody kept the old one, and the current
        name is the one every writer since the rename has touched.
        """
        for name in (STATE_FILENAME, LEGACY_STATE_FILENAME):
            candidate = spec_dir / name
            if candidate.is_file():
                return candidate
        return None

    @classmethod
    def load(cls, spec_dir: Path, work_item: str) -> "WorkItemState":
        """Load, or return a fresh state. A corrupt file is **kept**, not deleted
        (R8.3) — it may be the only record of what happened."""
        path = cls.existing_path(spec_dir)
        if path is None:
            return cls(work_item=work_item)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "%s is unreadable (%s); treating it as absent and reconstructing "
                "from the artifacts — the file is kept for post-mortem",
                path,
                exc,
            )
            return cls(work_item=work_item)
        if not isinstance(data, dict):
            logger.warning("%s is not an object; ignoring it", path)
            return cls(work_item=work_item)
        return cls(
            work_item=str(data.get("workItem", work_item)),
            current_node=str(data.get("currentNode", "")),
            nodes={
                k: NodeRecord.from_dict(v)
                for k, v in (data.get("nodes") or {}).items()
                if isinstance(v, dict)
            },
            decisions=dict(data.get("decisions") or {}),
            forced=list(data.get("forced") or []),
            parked=data.get("parked"),
            session=data.get("session"),
            completions=dict(data.get("completions") or {}),
            skips={
                k: dict(v)
                for k, v in (data.get("skips") or {}).items()
                if isinstance(v, dict)
            },
            opt_ins={
                k: dict(v)
                for k, v in (data.get("optIns") or {}).items()
                if isinstance(v, dict)
            },
            surface=str(data.get("surface") or ""),
            # A list, or nothing at all. A bare string is not half-read into
            # eight one-character repositories — the shape of `repositories`
            # itself refuses that, and a non-list here is *no declaration*.
            repos=_string_list(data.get("repos")),
            loop=str(data.get("loop") or ""),
            version=int(data.get("version", STATE_VERSION)),
        )

    def save(self, spec_dir: Path) -> Path:
        """Atomic write — temp file plus rename, so a crash never truncates it."""
        spec_dir.mkdir(parents=True, exist_ok=True)
        path = self.path_for(spec_dir)
        payload = json.dumps(self.as_dict(), indent=2, sort_keys=False) + "\n"
        fd, tmp = tempfile.mkstemp(dir=str(spec_dir), prefix=".work-item-state-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return path

    def as_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "workItem": self.work_item,
            "currentNode": self.current_node,
            "nodes": {k: v.as_dict() for k, v in self.nodes.items()},
            "decisions": self.decisions,
            "forced": self.forced,
            "parked": self.parked,
            "session": self.session,
            "completions": self.completions,
            "skips": self.skips,
            "optIns": self.opt_ins,
            "surface": self.surface,
            "repos": self.repos,
            "loop": self.loop,
        }

    # -- mutation -------------------------------------------------------------

    def record(self, node_id: str) -> NodeRecord:
        return self.nodes.setdefault(node_id, NodeRecord())

    def enter(self, node_id: str) -> None:
        rec = self.record(node_id)
        rec.entered_at = rec.entered_at or utc_now()
        rec.attempts += 1
        self.current_node = node_id
        self.parked = None

    def exit(self, node_id: str, outcome: str) -> None:
        rec = self.record(node_id)
        rec.outcome = outcome
        rec.exited_at = utc_now()

    def park(self, node_id: str, reason: str) -> None:
        self.parked = {"node": node_id, "reason": reason, "since": utc_now()}

    def note_block(self, node_id: str, message: str) -> bool:
        """Record a blocking message; True when it repeats the previous one.

        A repeat is the signal to escalate rather than retry a third time
        (R8.5) — the same finding twice means the agent is not converging.
        """
        rec = self.record(node_id)
        repeated = bool(message) and rec.last_block == message
        rec.last_block = message
        return repeated
