"""Durable, concurrency-safe registry linking work items to harness sessions.

One JSON file per session under the registry directory (default
``.the-loop/sessions/``, git-ignored) so entries are human-inspectable and
concurrent sessions never contend on a shared file. Writes are atomic
(tempfile + ``os.replace``). Stdlib only.

That directory is **shared** session-related state rather than this module's own
(issue-106 put the poll state and the control records there too), so listing
recognises the files the registry wrote — ``<slug>.json`` — and leaves the rest
alone (issue-111).

A second record type sits beside the session records under a ``.link.json``
suffix (issue-172): one per work item whose events are owned by *another* work
item's session — a pull request delivering an issue. It is the routing decision
written down, so that the binding stops being a value recomputed from ``gh`` on
every event.

Spec: docs/specs/issue-15/design.md §1 (requirement R2),
docs/specs/issue-172/design.md.
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

# GitHub's own owner/repo name shape, used to validate the names a browser URL is
# built from (issue-130). A name that is not this shape gets no URL at all: a
# link to the wrong repository is worse than no link.
_GITHUB_NAME_RE = re.compile(r"[A-Za-z0-9._-]+")

# A host in a ref (issue-130 review). Deliberately narrow — no scheme, no
# credentials, no path — because this value is interpolated into a URL. It must
# also be *recognisable* as a host, because it is what distinguishes a
# three-segment path (`host/owner/repo`) from a malformed two-segment one: a
# dotted name, or a name with an explicit port. `github:octo/repo/sub#15` is
# therefore rejected rather than quietly read as a work item on a host called
# "octo" — a silent second identity for something that was probably a typo.
_HOST_RE = re.compile(
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?::\d+)?"  # dotted, optional port
    r"|[A-Za-z0-9-]+:\d+"  # or a bare name with an explicit port
)

#: The host a ``github:`` ref means when it does not say (github.com). A ref
#: names its host only when it is somewhere else, so every ref written before
#: issue-130 keeps its exact form — and its file name.
DEFAULT_GITHUB_HOST = "github.com"

_SCHEME_HOST_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://(?:[^@/]+@)?([^/:]+(?::\d+)?)")

# The characters tmux rewrites in a session name, because they are its own target
# grammar (`session:window.pane`). See `tmux_session_name`.
_TMUX_TARGET_SYNTAX_RE = re.compile(r"[.:]")


def tmux_session_name(name: str) -> str:
    """``name`` as tmux would spell it — tmux's own ``session_check_name``.

    tmux rewrites ``.`` and ``:`` to ``_`` when it creates a session, because
    both are its target grammar (``session:window.pane``). Asking for
    ``loop-github-octo-foo.js-15`` therefore *creates* ``loop-…foo_js-15``, and
    handing the dotted spelling back is worse than a miss: tmux re-parses it into
    a different kind of target (``has-session -t loop-a.b-15`` answers ``can't
    find pane: b-15``). So the-loop never holds the pre-rewrite spelling — it
    applies tmux's rule at the two points a name enters: where one is minted
    (:meth:`the_loop.runner.TmuxRunner.target_for`) and where one is admitted
    from the registry (:meth:`Session.__post_init__`), which is what makes a
    record written before issue-154 address the session tmux actually created.

    Pure, total and idempotent. Note the rewrite is *not* injective — work items
    whose slugs differ only in a ``.``/``_`` position share one name — but neither
    is tmux's own namespace, which cannot host both at once either
    (docs/specs/issue-154/bugfix.md § Out of scope).
    """
    return _TMUX_TARGET_SYNTAX_RE.sub("_", name)


def host_from_url(url: str, default: str = DEFAULT_GITHUB_HOST) -> str:
    """The host in an ``html_url``/``clone_url``, or ``default`` when there is none.

    Both ingresses know which host an event came from — a webhook payload
    carries the repository's ``html_url``, and a polled item carries its own —
    so a work item on GitHub Enterprise can be identified as such at the point
    it enters the-loop, rather than assumed to be on github.com (issue-130
    review).
    """
    match = _SCHEME_HOST_RE.match(url or "")
    return match.group(1) if match else default


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

# Link records (issue-172) live in the same directory under a suffix the pattern
# above cannot admit: it requires a name ending ``-<number>.json``, and
# ``github-octo-repo-7.link.json`` ends ``.link.json``. That is what keeps
# ``list_sessions`` — and the "skipping unreadable registry file" warning, and
# ``reset --all``'s enumeration — untouched by their presence, with nothing
# taught about them.
_LINK_SUFFIX = ".link.json"
_LINK_FILE_RE = re.compile(r"[A-Za-z0-9._-]+-\d+\.link\.json")

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

    The path is ``[<host>/]<owner>/<repo>``: a work item on GitHub Enterprise
    names its host (``github:ghe.corp.example/owner/repo#15``), and one on
    github.com does not (issue-130 review). Keeping the default host *unwritten*
    is what makes this backwards compatible in the only two places that matter —
    every ref string already on disk still parses to the same work item, and
    :attr:`slug` still resolves to the same file name.

    The ``jira:`` prefix is reserved for the Jira follow-up (out of scope here).
    """

    provider: str
    owner: str
    repo: str
    number: int
    host: str = ""  # "" means the provider's default (see DEFAULT_GITHUB_HOST)

    def __post_init__(self) -> None:
        # Normalised so two refs for the same work item are equal (and hash
        # alike) whether or not the caller spelled the default host out. They
        # key the session registry and the poll ledger, so an unnormalised
        # duplicate would be a second identity for one work item.
        if self.provider == "github" and not self.host:
            object.__setattr__(self, "host", DEFAULT_GITHUB_HOST)

    @property
    def default_host(self) -> bool:
        """Whether this ref's host is the provider's default (so it is unwritten)."""
        return self.provider != "github" or self.host == DEFAULT_GITHUB_HOST

    @property
    def path(self) -> str:
        """``[<host>/]<owner>/<repo>`` — the host only when it is not the default."""
        prefix = "" if self.default_host else f"{self.host}/"
        return f"{prefix}{self.owner}/{self.repo}"

    @property
    def ref(self) -> str:
        return f"{self.provider}:{self.path}#{self.number}"

    @property
    def url(self) -> str:
        """The work item's browser URL, or ``""`` when none can be derived.

        The ref is the machine's name for a work item; this is the human's link to
        it (issue-130). Both are kept: a URL carries no provider prefix and cannot
        be parsed back into a ref without knowing each provider's layout.

        Derived, never guessed. Only ``github`` refs resolve — the host is the
        ref's own (github.com unless it says otherwise), and GitHub redirects
        ``/issues/<n>`` to ``/pull/<n>`` when the number is a pull request, so one
        form serves both. A host, owner or repo that is not the shape GitHub
        accepts yields ``""``, and the field is simply absent wherever it would
        have been written: a link to the wrong place is worse than no link.
        """
        if self.provider != "github":
            return ""
        if not (
            _HOST_RE.fullmatch(self.host)
            and _GITHUB_NAME_RE.fullmatch(self.owner)
            and _GITHUB_NAME_RE.fullmatch(self.repo)
        ):
            return ""
        return f"https://{self.host}/{self.owner}/{self.repo}/issues/{self.number}"

    @property
    def slug(self) -> str:
        """Filesystem-safe form used as the registry file name.

        Built from :attr:`path`, so a github.com work item's file name is exactly
        what it was before refs learned about hosts, and two work items with the
        same owner/repo/number on different hosts get different files.
        """
        raw = f"{self.provider}-{self.path.replace('/', '-')}-{self.number}"
        return re.sub(r"[^A-Za-z0-9._-]+", "-", raw)

    @classmethod
    def parse(cls, ref: str) -> "WorkItemRef":
        match = _REF_RE.match(ref.strip())
        if not match:
            raise ValueError(
                f"invalid work-item ref {ref!r}; expected "
                "<provider>:[<host>/]<owner>/<repo>#<number> "
                "(e.g. github:octo/repo#15, github:ghe.corp.example/octo/repo#15)"
            )
        parts = match.group("path").split("/")
        if len(parts) == 2:
            host, (owner, repo) = "", parts
        elif len(parts) == 3:
            host, owner, repo = parts
        else:
            raise ValueError(
                f"invalid work-item ref {ref!r}; expected <owner>/<repo>, "
                "optionally preceded by a host, before '#'"
            )
        if not owner or not repo or (host and not _HOST_RE.fullmatch(host)):
            raise ValueError(
                f"invalid work-item ref {ref!r}; expected <owner>/<repo>, "
                "optionally preceded by a host, before '#'"
            )
        return cls(
            provider=match.group("provider"),
            owner=owner,
            repo=repo,
            number=int(match.group("number")),
            host=host,
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
    # tmux session name hosting this session; "" until one is spawned (a
    # self-registered record gets its tmux session on first dispatch). The
    # per-record runner selector was removed with the process runner
    # (issue-156): tmux is the only runner.
    tmux_target: str = ""
    recent_deliveries: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # `tmuxTarget` is the name **tmux uses**, never the one the-loop asked
        # for. Normalising here rather than only where names are minted is what
        # makes a record written before issue-154 — holding the pre-rewrite
        # spelling of a session tmux had already renamed — address the real
        # session on the next read, with no migration and nothing to rename.
        if self.tmux_target:
            self.tmux_target = tmux_session_name(self.tmux_target)

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
            # A legacy record's "runner" key (pre-issue-156) is ignored: there
            # is nothing left to branch on.
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


@dataclass
class SessionLink:
    """A durable binding from one work-item ref to the ref whose session owns it.

    A pull request that delivers an issue's work item routes its events to that
    issue's session (issue-93). Before issue-172 that binding existed only as a
    value recomputed from ``gh`` on every cycle, so removing the link in GitHub's
    Development panel — or one failed listing — silently re-pointed routing at
    the PR itself, past a session that was still running and still owned the
    work. This record is the decision, written down at the moment it is made.

    :attr:`created_at` survives a re-point and :attr:`updated_at` does not, so
    the file answers the question an operator debugging a mis-routed event
    actually has: how long has this PR been bound, and when did that last change?
    """

    source: WorkItemRef  # the bound work item — in practice, the PR
    session_ref: WorkItemRef  # the work item whose session receives its events
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        data = {
            "ref": self.source.ref,
            "sessionRef": self.session_ref.ref,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        # Derived, never guessed — the same rule the portable record follows: a
        # ref that cannot yield a URL simply has no `url` field.
        url = self.source.url
        if url:
            data["url"] = url
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "SessionLink":
        """Parse a record. Raises when either end is not a work-item ref.

        Both ends go back through :meth:`WorkItemRef.parse`, so a hand-edited
        record holding a path, a shell fragment or anything else that is not
        ``<provider>:[<host>/]<owner>/<repo>#<number>`` raises here and is read
        as "no binding" by every caller — rather than reaching a lookup.
        """
        return cls(
            source=WorkItemRef.parse(data["ref"]),
            session_ref=WorkItemRef.parse(data["sessionRef"]),
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
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

    def _link_path_for(self, item: WorkItemRef) -> Path:
        return self.root / f"{item.slug}{_LINK_SUFFIX}"

    def _write_json(self, target: Path, payload: dict) -> None:
        """Atomically replace ``target`` with ``payload`` (tempfile + rename)."""
        self.root.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
            os.replace(tmp_name, target)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    def _write(self, session: Session) -> None:
        self._write_json(self._path_for(session.work_item), session.to_dict())

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

    def forget(self, work_item: Union[str, WorkItemRef]) -> bool:
        """Delete a work item's record entirely. False when there was none.

        The only method here that does not *transition* a record, and the reason
        `reset` differs from `close` (issue-137): a closed record still lists and
        is still reachable by ``sessions attach``, which is precisely the "the
        CLI still remembers this work item" a reset exists to end. Emits nothing
        — the reset emits one event for the whole work item rather than a partial
        trail per piece — and lets an ``OSError`` through for its caller to
        report.
        """
        try:
            self._path_for(_as_ref(work_item)).unlink()
        except FileNotFoundError:
            return False
        logger.info("forgot session record for %s", _as_ref(work_item).ref)
        return True

    # -- link records (issue-172) ------------------------------------------------

    def _read_link(self, path: Path) -> Optional[SessionLink]:
        try:
            return SessionLink.from_dict(json.loads(path.read_text()))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError) as exc:
            # "No binding" — never an exception into a dispatch path. An
            # unreadable or hand-edited record must degrade to the pre-issue-172
            # behaviour (derivation alone decides), not cost a delivery.
            logger.debug("ignoring unreadable link record %s: %s", path, exc)
            return None

    def link(
        self,
        source: Union[str, WorkItemRef],
        target: Union[str, WorkItemRef],
    ) -> Optional[SessionLink]:
        """Bind ``source``'s events to the session registered for ``target``.

        Returns the record when one was written, and ``None`` when there was
        nothing to write — a self-binding (refused) or a record that already
        names this target. Making "unchanged is a no-op" a property of the store
        rather than of every caller is what keeps a poll cycle from rewriting the
        same file, and re-emitting the same event, once per comment.

        ``createdAt`` is carried over when an existing binding is re-pointed, so
        only ``updatedAt`` moves.
        """
        source_ref, target_ref = _as_ref(source), _as_ref(target)
        if source_ref.ref == target_ref.ref:
            # A ref cannot deliver its own work item through someone else's
            # session. Refused here so no caller has to remember to check.
            return None
        existing = self._read_link(self._link_path_for(source_ref))
        if existing is not None and existing.session_ref.ref == target_ref.ref:
            return None
        now = _utcnow()
        record = SessionLink(
            source=source_ref,
            session_ref=target_ref,
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        self._write_json(self._link_path_for(source_ref), record.to_dict())
        logger.info(
            "bound %s to %s's session%s",
            source_ref.ref,
            target_ref.ref,
            f" (was {existing.session_ref.ref})" if existing is not None else "",
        )
        eventlog.emit(
            "session.linked",
            work_item=target_ref.ref,
            linked_ref=source_ref.ref,
            previous=existing.session_ref.ref if existing is not None else None,
        )
        return record

    def session_for(self, work_item: Union[str, WorkItemRef]) -> Optional[Session]:
        """The live session that owns this ref's events — record, then binding.

        The one question every ingress asks, answered in one place (issue-172).
        A ref with its own session resolves exactly as it always has, in a single
        read; the binding is consulted only where there is nothing to find, which
        is where a PR whose linkage GitHub no longer reports used to strand the
        session doing its work.

        Additive by construction: this can only return a session where
        :meth:`find_by_work_item` returned ``None``, so a stored binding never
        suppresses a session the derived linkage does find. Single-hop, because
        :meth:`resolve_link` does not recurse.
        """
        session = self.find_by_work_item(work_item)
        if session is not None:
            return session
        target = self.resolve_link(work_item)
        return self.find_by_work_item(target) if target is not None else None

    def resolve_link(self, source: Union[str, WorkItemRef]) -> Optional[WorkItemRef]:
        """The work item whose session owns ``source``'s events, or ``None``.

        **Single hop, on purpose.** A binding whose target is itself bound is not
        followed further: there is no legitimate chain to express, and refusing
        to traverse means no cycle can be constructed and no depth has to be
        bounded.
        """
        record = self._read_link(self._link_path_for(_as_ref(source)))
        return record.session_ref if record is not None else None

    def unlink(self, source: Union[str, WorkItemRef]) -> bool:
        """Delete ``source``'s binding. False when there was none.

        Emits, where :meth:`forget` deliberately does not. The difference is
        whose record is being removed: ``forget`` deletes the file named by the
        work item the reset is *about*, which the reset's own single event
        already names, while a reset also removes bindings filed under **other**
        work items' names — and nothing else in the trail would say which.
        """
        item = _as_ref(source)
        try:
            self._link_path_for(item).unlink()
        except FileNotFoundError:
            return False
        logger.info("removed the session binding for %s", item.ref)
        eventlog.emit("session.unlinked", work_item=item.ref)
        return True

    def list_links(self) -> List[SessionLink]:
        """Every readable link record in the registry directory, by file name."""
        links = []
        if self.root.is_dir():
            for path in sorted(self.root.glob(f"*{_LINK_SUFFIX}")):
                if not _LINK_FILE_RE.fullmatch(path.name):
                    continue
                record = self._read_link(path)
                if record is not None:
                    links.append(record)
        return links

    def links_to(self, target: Union[str, WorkItemRef]) -> List[SessionLink]:
        """Every binding naming ``target`` as the session-owning work item.

        The reverse direction is a scan, and deliberately so: it is only ever
        needed by ``sessions reset``, never by dispatch. Forward resolution —
        the hot path — stays a single read of a known path.
        """
        ref = _as_ref(target).ref
        return [link for link in self.list_links() if link.session_ref.ref == ref]

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
