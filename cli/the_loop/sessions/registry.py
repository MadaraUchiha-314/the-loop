"""Durable, concurrency-safe registry linking work items to harness sessions.

One JSON file per session under the registry directory (default
``.the-loop/sessions/``, git-ignored) so entries are human-inspectable and
concurrent sessions never contend on a shared file. Writes are atomic
(tempfile + ``os.replace``). Stdlib only.

That directory is **shared** session-related state rather than this module's own
(issue-106 put the poll state and the control records there too), so listing
recognises the files the registry wrote — ``<slug>.json`` — and leaves the rest
alone (issue-111).

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

from .. import eventlog

logger = logging.getLogger("the-loop.sessions")

# How many processed delivery ids each session keeps (restart-surviving dedup).
_RECENT_DELIVERIES_CAP = 50

_REF_RE = re.compile(r"^(?P<provider>[a-z][a-z0-9-]*):(?P<path>[^#]+)#(?P<number>\d+)$")

# GitHub's own owner/repo name shape, used to decide whether a browser URL can be
# derived from a ref (issue-130). ``_REF_RE`` accepts any non-``#`` text as the
# path and splits it at the FIRST slash, so ``repo`` may carry further segments —
# enough for an interpolated URL to point somewhere other than the work item it
# claims to describe. A name that is not this shape gets no URL at all.
_GITHUB_NAME_RE = re.compile(r"[A-Za-z0-9._-]+")

# The registry directory is shared session-related state, not this class's
# private space: the poll state sits beside these files by design (issue-106,
# ``state.StateLayout.poll_state``) and the control records in a subdirectory. So
# a directory scan must recognise the files the registry itself *wrote* rather
# than assume every ``*.json`` is a session record — otherwise a healthy
# neighbour is reported as a corrupt entry on every listing (issue-111).
# ``_write`` names each file ``<slug>.json`` and :attr:`WorkItemRef.slug` always
# ends in ``-<number>``, so this is a deliberate *superset* of what the registry
# produces: a session file can never fail it (the direction that matters — a
# false negative would hide a live session), while a name-shaped stranger that
# slips through is simply read and reported like any unparseable file.
_REGISTRY_FILE_RE = re.compile(r"[A-Za-z0-9._-]+-\d+\.json")

# Statuses that mean "this work item still has a session". A paused session
# (issue-106) is deliberately one of them: it is suppressed, not gone, so
# nothing may spawn a second session for the same work item while it exists.
LIVE_STATUSES = ("active", "paused")


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
    def url(self) -> str:
        """The work item's browser URL, or ``""`` when none can be derived.

        The ref is the machine's name for a work item; this is the human's link to
        it (issue-130). Both are kept: a URL carries no provider prefix and cannot
        be parsed back into a ref without knowing each provider's layout.

        Derived, never guessed. A ref carries no host, so only ``github`` refs
        resolve — to ``github.com``, which GitHub redirects to ``/pull/<n>`` when
        the number is a pull request, so one form serves both. Anything else, and
        any owner/repo that is not GitHub's own name shape, yields ``""`` and the
        field is simply absent wherever it would have been written.
        """
        if self.provider != "github":
            return ""
        if not (
            _GITHUB_NAME_RE.fullmatch(self.owner)
            and _GITHUB_NAME_RE.fullmatch(self.repo)
        ):
            return ""
        return f"https://github.com/{self.owner}/{self.repo}/issues/{self.number}"

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
    status: str = "active"  # active | paused (issue-106) | closed
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

    @property
    def is_live(self) -> bool:
        """Whether this session still owns its work item (active or paused)."""
        return self.status in LIVE_STATUSES

    @property
    def is_paused(self) -> bool:
        return self.status == "paused"


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
        eventlog.emit(
            "session.registered",
            work_item=session.work_item.ref,
            harness=session.harness,
            harness_session_id=session.harness_session_id,
            runner=session.runner,
            cwd=session.cwd,
            replaced=bool(existing is not None and force) or None,
        )
        return session

    def find_by_work_item(
        self, work_item: Union[str, WorkItemRef], include_closed: bool = False
    ) -> Optional[Session]:
        """Return the **live** session for the work item, if any.

        Live is ``active`` *or* ``paused`` (issue-106): a paused session is
        suppressed, not gone, so every caller asking "does this work item have a
        session?" — the duplicate-registration guard, dispatch matching, the
        poller — correctly counts it as one. The few callers that must tell them
        apart read :attr:`Session.is_paused`.

        ``include_closed`` also returns a closed record — used by
        ``sessions attach`` to reach a tmux session retained after the work
        completed (issue-86). Dispatch never passes it: a closed session is
        not a routing target.
        """
        path = self._path_for(_as_ref(work_item))
        if not path.is_file():
            return None
        session = self._read(path)
        if session is None or not (session.is_live or include_closed):
            return None
        return session

    def list_sessions(self, status: Optional[str] = None) -> List[Session]:
        """Every session in the registry directory, optionally filtered by status.

        Only the files the registry wrote are considered (``_REGISTRY_FILE_RE``):
        the directory is shared with other session-related state, and a
        neighbour is not a corrupt entry.
        """
        sessions = []
        if self.root.is_dir():
            for path in sorted(self.root.glob("*.json")):
                if not _REGISTRY_FILE_RE.fullmatch(path.name):
                    # Someone else's file in a directory we share — not corruption.
                    logger.debug("ignoring non-registry file %s", path)
                    continue
                session = self._read(path)
                if session is not None and (status is None or session.status == status):
                    sessions.append(session)
        return sessions

    def pause(self, work_item: Union[str, WorkItemRef]) -> Optional[Session]:
        """Suppress delivery to this work item's session (issue-106).

        Returns the paused session, or ``None`` when there was no live session
        (or it was already paused) — the caller reports that as a no-op rather
        than an error: pausing something that is not running is not a failure.
        """
        session = self.find_by_work_item(work_item)
        if session is None or session.is_paused:
            return None
        session.status = "paused"
        self._write(session)
        logger.info("paused session %s", session.work_item.ref)
        eventlog.emit(
            "session.paused",
            work_item=session.work_item.ref,
            harness=session.harness,
            harness_session_id=session.harness_session_id,
        )
        return session

    def resume(self, work_item: Union[str, WorkItemRef]) -> Optional[Session]:
        """Return a paused session to ``active``; ``None`` when none was paused.

        Nothing is replayed: events suppressed while paused are not queued up
        (the harness re-reads the thread itself, as it does for anything that
        happened before its session existed).
        """
        session = self.find_by_work_item(work_item)
        if session is None or not session.is_paused:
            return None
        session.status = "active"
        self._write(session)
        logger.info("resumed session %s", session.work_item.ref)
        eventlog.emit(
            "session.resumed",
            work_item=session.work_item.ref,
            harness=session.harness,
            harness_session_id=session.harness_session_id,
        )
        return session

    def close(self, work_item: Union[str, WorkItemRef]) -> bool:
        """Mark the session closed. Returns False when nothing was live.

        Closes a ``paused`` session as readily as an ``active`` one — pausing
        must never leak an agent past the end of its work item.
        """
        session = self.find_by_work_item(work_item)
        if session is None:
            return False
        session.status = "closed"
        self._write(session)
        logger.info("closed session %s", session.work_item.ref)
        eventlog.emit(
            "session.closed",
            work_item=session.work_item.ref,
            harness=session.harness,
            harness_session_id=session.harness_session_id,
        )
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
