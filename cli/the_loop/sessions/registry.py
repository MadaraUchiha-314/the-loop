"""Durable, concurrency-safe registry linking work items to harness sessions.

One JSON file per session under the registry directory (default
``.the-loop/sessions/``, git-ignored) so entries are human-inspectable and
concurrent sessions never contend on a shared file. Writes are atomic
(tempfile + ``os.replace``). Stdlib only.

That directory is **shared** session-related state rather than this module's own
(issue-106 put the poll state and the control records there too), so listing
recognises the files the registry wrote — ``<slug>.json`` — and leaves the rest
alone (issue-111).

A work item's record also carries its **pull requests** (issue-172): one entry
per PR that delivers it, each an endpoint in its own right — and, when
``routing.tmux.sessionPerPr`` makes that PR a candidate *and* a checkout of its
own can be prepared for it, its own tmux session and harness conversation. That
list is the routing decision written down, so which session owns a PR's events
stops being a value recomputed from ``gh`` on every event.

One file per work item is the point: everything about a work item — its own
session, every PR delivering it, and every tmux/harness conversation involved —
is answerable by reading one record (PR #173 review).

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


def is_github_name(value: str) -> bool:
    """Whether ``value`` is a shape GitHub accepts as an owner or repository name.

    Public because a second caller needs the same answer (issue-194): deriving a
    ref from the harness config's ``ticketing.github`` validates owner and repo
    before building anything, and "what GitHub accepts" must have **one**
    definition — two copies of this expression is how one of them ends up
    accepting a `/` and pointing a comment at the wrong repository.
    """
    return bool(_GITHUB_NAME_RE.fullmatch(value))


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


def is_github_host(value: str) -> bool:
    """Whether ``value`` is the shape of a GitHub host — the one grammar for a host.

    Public since issue-311: the host resolver (``ghhost``), ``ref_for``, a poll
    source's ``[HOST/]OWNER/REPO`` and a kickoff slug all refuse through this one
    expression **before** a value is interpolated into a URL or a ``--hostname``
    argument. Two copies of it is how one of them comes to accept a scheme.
    """
    return bool(_HOST_RE.fullmatch(value or ""))


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
            and is_github_name(self.owner)
            and is_github_name(self.repo)
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
    """One harness session, and the work item or pull request it serves.

    Two roles, one type, on purpose (issue-172, PR #173 review). A **record** is
    a work item's session — the file in the registry directory. An **endpoint**
    is one addressable harness conversation, and a record holds one for the work
    item itself plus one per pull request in :attr:`pull_requests`. A PR endpoint
    is a ``Session`` whose ``work_item`` is the PR's ref, which is what lets the
    whole dispatch path — deliver, respawn, resume, close — operate on either
    without knowing which it has.

    Only a record carries :attr:`pull_requests`; endpoints nested inside one
    always have it empty. The nesting is one level deep and stays that way: a PR
    does not have pull requests.
    """

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
    #: Endpoints for the pull requests delivering this work item (issue-172).
    #: Empty on an endpoint; empty on a record until a PR event routes here.
    pull_requests: List["Session"] = field(default_factory=list)

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
        data = {
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
        url = item.url
        if url:
            # The human's link to the thing this endpoint serves — same
            # derive-never-guess rule the portable record follows.
            data["url"] = url
        if self.pull_requests:
            # Absent rather than `[]` on a record with no PRs, so every session
            # file written before issue-172 round-trips byte-identically.
            data["pullRequests"] = [pr.to_dict() for pr in self.pull_requests]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        # One level only: a nested endpoint's own `pullRequests` is dropped
        # rather than recursed into, so a hand-edited record cannot build a
        # tree for the resolver to walk. An entry that does not parse is
        # skipped for the same reason `_read` skips an unreadable file — a
        # hand-edited PR entry must degrade to "that PR is unrecorded", never
        # take the work item's own session down with it.
        pull_requests = []
        for pr in data.get("pullRequests") or []:
            try:
                pull_requests.append(cls.from_dict({**(pr or {}), "pullRequests": []}))
            except (ValueError, KeyError, TypeError) as exc:
                logger.debug("skipping unreadable pullRequests entry: %s", exc)
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
            pull_requests=pull_requests,
        )

    @property
    def is_live(self) -> bool:
        """Whether this session still owns its work item (active or paused)."""
        return self.status in LIVE_STATUSES

    @property
    def is_paused(self) -> bool:
        return self.status == "paused"

    def endpoint_for(self, ref: Union[str, WorkItemRef]) -> Optional["Session"]:
        """The endpoint serving ``ref`` — this session itself, or one of its PRs.

        ``None`` when ``ref`` is neither. Identity is by ref string, so a caller
        holding a freshly-parsed ref finds the endpoint a previous cycle wrote.
        """
        wanted = _as_ref(ref).ref
        if self.work_item.ref == wanted:
            return self
        for pr in self.pull_requests:
            if pr.work_item.ref == wanted:
                return pr
        return None

    def owns(self, ref: Union[str, WorkItemRef]) -> bool:
        """Whether this record serves ``ref`` — as itself or as one of its PRs."""
        return self.endpoint_for(ref) is not None


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

    # -- pull-request endpoints (issue-172) --------------------------------------

    def record_owning(self, ref: Union[str, WorkItemRef]) -> Optional[Session]:
        """The live record serving ``ref`` — as its work item, or as one of its PRs.

        Two lookups, cheapest first. A ref with its own record resolves in one
        read of a known path, which is every issue event and every PR that is its
        own work item. Only a ref with no record of its own costs the scan, and
        the scan is over the live work items on this machine — a handful of small
        files — not over anything that grows with history (PR #173 review).
        """
        item = _as_ref(ref)
        own = self.find_by_work_item(item)
        if own is not None:
            return own
        for session in self.list_sessions():
            if session.is_live and session.owns(item):
                return session
        return None

    def session_for(
        self,
        ref: Union[str, WorkItemRef],
        session_per_pr: bool = True,
    ) -> Optional[Session]:
        """The live **endpoint** that owns this ref's events, or ``None``.

        The question every ingress asks. For a work item that is its own record
        this is unchanged from before issue-172; for a pull request it is the PR's
        own endpoint, and ``session_per_pr=False`` collapses it onto the record's
        own session instead — the pre-issue-172 behaviour, kept as a configured
        choice rather than discarded.

        Policy is the caller's: the store is told which it wants and never reads
        configuration itself. Deliberately still a **boolean** while
        ``routing.tmux.sessionPerPr`` has three values (issue-258): the store
        resolves a ref to the endpoint that *exists*, and an endpoint only exists
        for a pull request the dispatcher already decided to split. The caller
        passes ``TmuxConfig.splits_pull_requests``; teaching the store the
        repository rule as well would put one decision in two places.
        """
        record = self.record_owning(ref)
        if record is None:
            return None
        endpoint = record.endpoint_for(ref) if session_per_pr else record
        if endpoint is None or not endpoint.is_live:
            # A PR whose endpoint was closed with its pull request falls back to
            # the work item's own session: the work item is still open, and its
            # session is still the one that owns the work.
            return record if record.is_live else None
        return endpoint

    def link_pull_request(
        self,
        owner: Union[str, WorkItemRef],
        pr: Union[str, WorkItemRef],
    ) -> Optional[Session]:
        """Record that ``pr`` delivers ``owner``'s work item.

        Returns the PR's endpoint when one was added, and ``None`` when there was
        nothing to do — the record is gone, the refs are the same work item, or
        the PR is already listed. Making "already known is a no-op" a property of
        the store is what stops a poll cycle rewriting the file, and re-emitting
        the same event, once per comment.

        The endpoint starts with no tmux target and no conversation id: it is a
        statement about *which* PRs deliver this work item, and the first event
        that needs a session for one spawns it.
        """
        owner_ref, pr_ref = _as_ref(owner), _as_ref(pr)
        if owner_ref.ref == pr_ref.ref:
            # A work item does not deliver itself.
            return None
        record = self.find_by_work_item(owner_ref)
        if record is None or record.endpoint_for(pr_ref) is not None:
            return None
        endpoint = Session(
            work_item=pr_ref,
            harness=record.harness,
            harness_session_id="",
            cwd=record.cwd,
            created_at=_utcnow(),
        )
        record.pull_requests.append(endpoint)
        self._write(record)
        logger.info(
            "recorded %s as a pull request delivering %s", pr_ref.ref, owner_ref.ref
        )
        eventlog.emit(
            "session.pr_linked",
            work_item=owner_ref.ref,
            pull_request=pr_ref.ref,
        )
        return endpoint

    def save_endpoint(self, owner: Union[str, WorkItemRef], endpoint: Session) -> None:
        """Persist ``endpoint`` back into ``owner``'s record.

        The one write path the dispatcher needs, and the reason a PR endpoint can
        be a plain :class:`Session` everywhere else: the caller hands back
        whichever endpoint it was working on, and this decides whether that means
        the record's own fields or an entry in ``pullRequests``.
        """
        owner_ref = _as_ref(owner)
        record = self.find_by_work_item(owner_ref)
        if record is None:
            return
        if endpoint.work_item.ref == owner_ref.ref:
            endpoint.pull_requests = record.pull_requests
            self._write(endpoint)
            return
        replaced = [
            endpoint if pr.work_item.ref == endpoint.work_item.ref else pr
            for pr in record.pull_requests
        ]
        if all(
            pr.work_item.ref != endpoint.work_item.ref for pr in record.pull_requests
        ):
            replaced.append(endpoint)
        record.pull_requests = replaced
        self._write(record)

    def close_endpoint(
        self, owner: Union[str, WorkItemRef], ref: Union[str, WorkItemRef]
    ) -> Optional[Session]:
        """Mark one pull request's endpoint closed, leaving the record live.

        This is issue-101's rule falling out of the model rather than being
        special-cased: a PR merging ends *that* conversation, and the work item's
        session keeps running because a work item may be delivered by several PRs.
        Returns the closed endpoint so the caller can tear down its tmux session.
        """
        owner_ref, pr_ref = _as_ref(owner), _as_ref(ref)
        record = self.find_by_work_item(owner_ref)
        if record is None or owner_ref.ref == pr_ref.ref:
            return None
        endpoint = record.endpoint_for(pr_ref)
        if endpoint is None or endpoint is record or not endpoint.is_live:
            return None
        endpoint.status = "closed"
        self._write(record)
        logger.info("closed the endpoint for %s on %s", pr_ref.ref, owner_ref.ref)
        eventlog.emit(
            "session.pr_closed",
            work_item=owner_ref.ref,
            pull_request=pr_ref.ref,
            harness_session_id=endpoint.harness_session_id or None,
        )
        return endpoint

    def touch(
        self,
        work_item: Union[str, WorkItemRef],
        delivery_id: Optional[str] = None,
        endpoint_ref: Optional[Union[str, WorkItemRef]] = None,
    ) -> None:
        """Record a processed event (last-event timestamp + delivery id).

        ``endpoint_ref`` names which endpoint handled it; omitted means the work
        item's own. Restart-surviving dedup is therefore per-endpoint, which is
        what it has to be once one work item has several conversations: an id
        delivered into a PR's session must not read as already-processed for the
        work item's.
        """
        record = self.find_by_work_item(work_item)
        if record is None:
            return
        endpoint = record.endpoint_for(endpoint_ref or record.work_item) or record
        endpoint.last_event_at = _utcnow()
        if delivery_id:
            endpoint.recent_deliveries.append(delivery_id)
            del endpoint.recent_deliveries[:-_RECENT_DELIVERIES_CAP]
        self._write(record)
