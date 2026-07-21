"""Durable, concurrency-safe registry linking work items to harness sessions.

One JSON file per session under the registry directory (default
``.the-loop/sessions/``, git-ignored) so entries are human-inspectable and
concurrent sessions never contend on a shared file. Writes are atomic
(tempfile + ``os.replace``). Stdlib only.

Spec: docs/specs/issue-15/design.md §1 (requirement R2).
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Union

logger = logging.getLogger("the-loop.sessions")

# How many processed delivery ids each session keeps (restart-surviving dedup).
_RECENT_DELIVERIES_CAP = 50

_REF_RE = re.compile(r"^(?P<provider>[a-z][a-z0-9-]*):(?P<path>[^#]+)#(?P<number>\d+)$")


class RegistryError(Exception):
    """A registry invariant was violated (e.g. duplicate active session)."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class WorkItemRef:
    """A provider-qualified work-item reference, e.g. ``github:owner/repo#15``.

    The ``jira:`` prefix is reserved for the Jira follow-up (out of scope here).
    """

    provider: str
    owner: str
    repo: str
    number: int

    @property
    def ref(self) -> str:
        return f"{self.provider}:{self.owner}/{self.repo}#{self.number}"

    @property
    def slug(self) -> str:
        """Filesystem-safe form used as the registry file name."""
        raw = f"{self.provider}-{self.owner}-{self.repo}-{self.number}"
        return re.sub(r"[^A-Za-z0-9._-]+", "-", raw)

    @classmethod
    def parse(cls, ref: str) -> "WorkItemRef":
        match = _REF_RE.match(ref.strip())
        if not match:
            raise ValueError(
                f"invalid work-item ref {ref!r}; expected "
                "<provider>:<owner>/<repo>#<number> (e.g. github:octo/repo#15)"
            )
        path = match.group("path")
        owner, sep, repo = path.partition("/")
        if not sep or not owner or not repo:
            raise ValueError(
                f"invalid work-item ref {ref!r}; expected <owner>/<repo> before '#'"
            )
        return cls(
            provider=match.group("provider"),
            owner=owner,
            repo=repo,
            number=int(match.group("number")),
        )


@dataclass
class Session:
    """One harness session working one work item (see design.md data model)."""

    work_item: WorkItemRef
    harness: str  # "claude" | "cursor"
    harness_session_id: str  # claude session_id | cursor chat id
    cwd: str  # where resume must run (worktree-aware)
    status: str = "active"  # active | closed
    created_at: str = ""
    last_event_at: Optional[str] = None
    runner: str = "process"  # process | tmux (issue-32)
    tmux_target: str = ""  # tmux session name when runner == "tmux"
    recent_deliveries: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        item = self.work_item
        return {
            "workItem": {
                "ref": item.ref,
                "provider": item.provider,
                "owner": item.owner,
                "repo": item.repo,
                "number": item.number,
            },
            "harness": self.harness,
            "harnessSessionId": self.harness_session_id,
            "cwd": self.cwd,
            "status": self.status,
            "createdAt": self.created_at,
            "lastEventAt": self.last_event_at,
            "runner": self.runner,
            "tmuxTarget": self.tmux_target,
            "recentDeliveries": self.recent_deliveries,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(
            work_item=WorkItemRef.parse(data["workItem"]["ref"]),
            harness=data["harness"],
            harness_session_id=data["harnessSessionId"],
            cwd=data["cwd"],
            status=data.get("status", "active"),
            created_at=data.get("createdAt", ""),
            last_event_at=data.get("lastEventAt"),
            runner=data.get("runner", "process"),
            tmux_target=data.get("tmuxTarget", ""),
            recent_deliveries=list(data.get("recentDeliveries") or []),
        )


def _as_ref(work_item: Union[str, WorkItemRef]) -> WorkItemRef:
    if isinstance(work_item, WorkItemRef):
        return work_item
    return WorkItemRef.parse(work_item)


class SessionRegistry:
    """File-per-session store under ``root`` with atomic writes."""

    def __init__(self, root: Union[str, Path]):
        self.root = Path(root)

    # -- storage primitives ----------------------------------------------------

    def _path_for(self, item: WorkItemRef) -> Path:
        return self.root / f"{item.slug}.json"

    def _write(self, session: Session) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        target = self._path_for(session.work_item)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(session.to_dict(), handle, indent=2)
                handle.write("\n")
            os.replace(tmp_name, target)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    def _read(self, path: Path) -> Optional[Session]:
        try:
            return Session.from_dict(json.loads(path.read_text()))
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("skipping unreadable registry file %s: %s", path, exc)
            return None

    # -- public API (design.md §1) ----------------------------------------------

    def register(self, session: Session, force: bool = False) -> Session:
        """Persist ``session``. One active session per work item (R2.3)."""
        existing = self.find_by_work_item(session.work_item)
        if existing is not None and not force:
            raise RegistryError(
                f"an active session already exists for {session.work_item.ref} "
                f"(harness={existing.harness}, id={existing.harness_session_id}); "
                "use force to replace it"
            )
        if not session.created_at:
            session.created_at = _utcnow()
        self._write(session)
        logger.info(
            "registered session %s -> %s:%s (cwd=%s)",
            session.work_item.ref,
            session.harness,
            session.harness_session_id,
            session.cwd,
        )
        return session

    def find_by_work_item(
        self, work_item: Union[str, WorkItemRef]
    ) -> Optional[Session]:
        """Return the ``active`` session for the work item, if any."""
        path = self._path_for(_as_ref(work_item))
        if not path.is_file():
            return None
        session = self._read(path)
        if session is None or session.status != "active":
            return None
        return session

    def list_sessions(self, status: Optional[str] = None) -> List[Session]:
        sessions = []
        if self.root.is_dir():
            for path in sorted(self.root.glob("*.json")):
                session = self._read(path)
                if session is not None and (status is None or session.status == status):
                    sessions.append(session)
        return sessions

    def close(self, work_item: Union[str, WorkItemRef]) -> bool:
        """Mark the session closed. Returns False when nothing was active."""
        session = self.find_by_work_item(work_item)
        if session is None:
            return False
        session.status = "closed"
        self._write(session)
        logger.info("closed session %s", session.work_item.ref)
        return True

    def touch(
        self,
        work_item: Union[str, WorkItemRef],
        delivery_id: Optional[str] = None,
    ) -> None:
        """Record a processed event (last-event timestamp + delivery id)."""
        session = self.find_by_work_item(work_item)
        if session is None:
            return
        session.last_event_at = _utcnow()
        if delivery_id:
            session.recent_deliveries.append(delivery_id)
            del session.recent_deliveries[:-_RECENT_DELIVERIES_CAP]
        self._write(session)
