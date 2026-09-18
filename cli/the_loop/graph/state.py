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
    "PR_LINKED_BY",
    "PR_STATES",
    "STATE_FILENAME",
    "PullRequest",
    "StateLockBusy",
    "WorkItemState",
    "state_lock",
    "utc_now",
]

STATE_FILENAME = "work-item-state.json"
LOCK_FILENAME = "work-item-state.lock"

#: What a pull request's upstream state may be (issue-368, R2.2). Written by the
#: daemon's one close path; ``open`` until it says otherwise.
PR_STATES = ("open", "merged", "closed")

#: Who recorded that a pull request delivers this work item. The **read**
#: vocabulary: ``"session"`` is the only value the-loop writes (issue-370, R2.1)
#: — the session that opened the pull request said so, through
#: ``the-loop sessions link-pr``. ``"event"`` is kept because a file written
#: before that change carries rows the first routing event added, and they must
#: keep loading, and keep saying what they say. Nothing mints it any more.
PR_LINKED_BY = ("session", "event")

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


def _pull_requests(raw: Any, origin: str = "") -> List["PullRequest"]:
    """Usable pull-request entries from a list, deduplicated by ref.

    An entry that does not parse is skipped rather than raising: a hand-edited
    record must degrade to "that pull request is unrecorded", never take the
    work item's whole pointer down with it.
    """
    if not isinstance(raw, (list, tuple)):
        return []
    found: Dict[str, PullRequest] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        parsed = PullRequest.from_dict(entry, origin=origin)
        if parsed is not None:
            found.setdefault(parsed.ref, parsed)
    return list(found.values())


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class PullRequest:
    """One pull request delivering this work item (issue-368, R2.1).

    A **remote entity of the repository**, so it is recorded here rather than in
    the machine-local session record, which is where the only copy used to be:
    `local/<slug>.json`'s `pullRequests[]` never travels, so a hand-off lost
    which pull requests delivered an item and re-derived them from `gh`'s
    closing references — the inference issue-172 stopped trusting.

    `state` is the *upstream* state (open/merged/closed), written by the
    daemon's one close path; the session endpoint's `status` stays a handle's
    status. `state_dir` is the inner loop's directory relative to the spec
    directory, derived at write so a reader needs no code to find it.
    """

    ref: str
    repository: str = ""
    number: int = 0
    url: str = ""
    state_dir: str = ""
    state: str = "open"
    linked_at: str = ""
    linked_by: str = "session"
    #: This pull request **is** the work item, rather than delivering it
    #: (issue-370, R7.1). `the-loop review` and `the-loop contribute` are armed
    #: on a pull request, and the abstract entity the-loop manages is a work
    #: item whatever represents it — a GitHub issue, a Jira story, a pull
    #: request. So the pull request is recorded here the same way any other is,
    #: and this marker is what tells a reader which of the two relations it has
    #: without comparing refs. A marked row carries **no** ``stateDir``: the
    #: work item's own directory is the loop, so there is no inner loop to
    #: point at, and deriving one would nest a copy of the work item inside
    #: itself.
    is_self: bool = False

    def as_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "ref": self.ref,
            "repository": self.repository,
            "number": self.number,
            "url": self.url,
            "stateDir": self.state_dir,
            "state": self.state,
            "linkedAt": self.linked_at,
            "linkedBy": self.linked_by,
        }
        if self.is_self:
            # Absent rather than `false`, the rule the rest of this file
            # follows: every row written before issue-370 round-trips
            # byte-identically, and a reader can tell "delivers it" from
            # "written before the marker existed".
            data["self"] = True
        return data

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], origin: str = ""
    ) -> Optional["PullRequest"]:
        """One entry, or ``None`` when it is not usable.

        Every field is re-validated on the way in, because this file is
        agent-writable and proposable by anyone who can open a pull request
        against the origin repository. A `repository` that is not a usable
        repository path, or a `state_dir` that is not the one this repository
        and number derive, is refused — the entry is skipped and the rest of the
        file is honoured, the rule `Session.from_dict` already follows for a
        hand-edited endpoint.
        """
        ref = str(data.get("ref") or "").strip()
        if not ref:
            return None
        repository = str(data.get("repository") or "").strip()
        if repository:
            from .hooks.loops import repo_state_key

            try:
                repo_state_key(repository)
            except ValueError:
                logger.warning(
                    "skipping the pull-request entry %s: %r is not a usable "
                    "repository path",
                    ref,
                    repository,
                )
                return None
        try:
            number = int(data.get("number") or 0)
        except (TypeError, ValueError):
            return None
        state = str(data.get("state") or "open")
        linked_by = str(data.get("linkedBy") or "event")
        # A `stateDir` is honoured only when it is one of the two spellings this
        # repository and number actually derive — the shipped `pr-loops/pr-<n>`
        # for a pull request in the work item's own repository, or the
        # qualified `pr-loops/<owner>__<repo>/pr-<n>` for one elsewhere
        # (issue-183). Anything else is a path the loop's own rules did not
        # build, so it is refused and recomputed rather than read as given.
        stored = str(data.get("stateDir") or "")
        spellings = {
            _pr_state_dir(repository, number, repository),
            _pr_state_dir(repository, number, ""),
        } - {""}
        state_dir = (
            stored if stored in spellings else _pr_state_dir(repository, number, origin)
        )
        # The work item's own pull request has no inner loop (issue-370, R7.1),
        # so any `stateDir` on that row is refused outright rather than
        # recomputed: the one this repository and number would derive points
        # inside the work item's own directory.
        is_self = bool(data.get("self"))
        if is_self:
            state_dir = ""
        return cls(
            ref=ref,
            repository=repository,
            number=number,
            url=str(data.get("url") or ""),
            # Derived, never read as given: a `stateDir` from the file would be a
            # path this repository's own rules did not build (issue-183's
            # filesystem boundary), so it is recomputed from the two values that
            # did go through that boundary.
            state_dir=state_dir,
            state=state if state in PR_STATES else "open",
            linked_at=str(data.get("linkedAt") or ""),
            linked_by=linked_by if linked_by in PR_LINKED_BY else "event",
            is_self=is_self,
        )


def repository_of(ref: str) -> str:
    """``github:octo/app#15`` → ``octo/app``; ``""`` when the ref will not parse.

    The work item's **origin** repository, which is what decides whether a pull
    request's inner loop keeps the shipped ``pr-loops/pr-<n>`` layout or the
    qualified one (issue-183).
    """
    from ..sessions import WorkItemRef

    try:
        return WorkItemRef.parse(ref).path
    except ValueError:
        return ""


def _pr_state_dir(repository: str, number: int, origin: str = "") -> str:
    """``pr-loops/[<owner>__<repo>/]pr-<n>`` for this pull request, or ``""``.

    The one spelling of an inner loop's directory, so the recorded value and the
    directory the runtime actually writes into cannot drift apart. A pull request
    in the work item's **own** repository keeps the shipped unqualified layout,
    exactly as ``Runtime`` and ``GraphLink`` build it; an unusable repository
    yields ``""`` rather than a guess.
    """
    if not number:
        return ""
    from .hooks.loops import inner_loop_state_dir

    qualifier = "" if (origin and repository == origin) else repository
    try:
        return inner_loop_state_dir(Path(), number, qualifier).as_posix()
    except ValueError:
        return ""


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
    #: The phase the walk is in (issue-378) — the phase of the last node entered
    #: that declares one, i.e. what the ``loop:<phase>`` label says. Written on
    #: every transition so the lifecycle events follow the label exactly, a
    #: node without a phase inheriting the one before it. Additive: absent in
    #: an older file, where the runtime derives it from the node records.
    phase: str = ""
    #: How many tmux+harness sessions this work item's pull requests get
    #: (issue-260), which model they run on and at what effort (issue-358) —
    #: frozen by the authorized reply at `phase-selection`, beside every other
    #: per-work-item choice (issue-368, R4.1). ``""`` is *no choice*, a
    #: different recorded fact from "the operator's default", and the daemon
    #: re-validates each on the way in: a model against what the operator
    #: declares now and against this machine's verdicts, a mode against the
    #: three-value vocabulary. They lived only in the portable record until
    #: issue-368, which left this file unable to say what its own work item runs
    #: on.
    session_per_pr: str = ""
    model: str = ""
    effort: str = ""
    #: The pull requests delivering this work item (issue-368, R2.1) — the
    #: repository's own objects, so they are recorded on the work item's branch
    #: rather than only in a machine-local session record that never travels.
    pull_requests: List[PullRequest] = field(default_factory=list)
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
            # `session` is deliberately NOT read (issue-368, R3.3). A harness
            # conversation id is a handle to one machine; it was written here
            # until this change, and a checked-in id may be anyone's — so a
            # legacy block is ignored on load and absent on the next save, and
            # `session: inherit` asks the session registry instead.
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
            phase=str(data.get("phase") or ""),
            session_per_pr=str(data.get("sessionPerPr") or ""),
            model=str(data.get("model") or ""),
            effort=str(data.get("effort") or ""),
            pull_requests=_pull_requests(
                data.get("pullRequests"),
                repository_of(str(data.get("workItem", work_item))),
            ),
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
            "completions": self.completions,
            "skips": self.skips,
            "optIns": self.opt_ins,
            "surface": self.surface,
            "sessionPerPr": self.session_per_pr,
            "model": self.model,
            "effort": self.effort,
            "repos": self.repos,
            "pullRequests": [pr.as_dict() for pr in self.pull_requests],
            "loop": self.loop,
            "phase": self.phase,
        }

    # -- pull requests (issue-368) --------------------------------------------

    def pull_request(self, ref: str) -> Optional[PullRequest]:
        """This work item's entry for ``ref``, or ``None``."""
        for entry in self.pull_requests:
            if entry.ref == ref:
                return entry
        return None

    def link_pr(
        self,
        ref: str,
        repository: str = "",
        number: int = 0,
        url: str = "",
        linked_by: str = "session",
        is_self: bool = False,
    ) -> Optional[PullRequest]:
        """Record that ``ref`` delivers this work item; ``None`` when it already did.

        **One writer** (issue-370, R2.1): the session that opened the pull
        request, through ``the-loop sessions link-pr``. This list is checked in,
        reviewed and carried to the next machine, so a row in it has to be a
        thing the-loop did — not a thing it inferred from a branch name or a
        closing keyword anyone can author. The first routing event used to write
        here too; it no longer does.

        ``is_self`` records the **other** relation a pull request can have to a
        work item (issue-370, R7.1): it *is* the work item, because
        ``the-loop review`` or ``the-loop contribute`` was armed on it. The two
        are recorded the same way, in the same list, so every reader of "which
        pull requests does this work item involve?" gets one answer whether the
        work item is an issue or a pull request; :attr:`PullRequest.is_self` is
        what distinguishes them. Without the flag a work item still does not
        **deliver** itself, and the self ref is refused as it always was.

        Idempotent by ref, like the registry's own ``link_pull_request``, so
        re-running the link after a retry costs nothing. Refuses an entry that
        does not validate (an unusable repository path), because this value
        becomes a directory name.
        """
        if not ref or self.pull_request(ref) is not None:
            return None
        if ref == self.work_item and not is_self:
            return None
        entry = PullRequest.from_dict(
            {
                "ref": ref,
                "repository": repository,
                "number": number,
                "url": url,
                "state": "open",
                "linkedAt": utc_now(),
                "linkedBy": linked_by,
                **({"self": True} if is_self else {}),
            },
            origin=repository_of(self.work_item),
        )
        if entry is None:
            return None
        self.pull_requests.append(entry)
        return entry

    def set_pr_state(self, ref: str, state: str) -> Optional[PullRequest]:
        """Record a pull request's upstream state; ``None`` when it is unknown here.

        The *upstream* fact — merged or closed — which is the repository's, not
        the machine's: the session endpoint's own ``status`` stays a handle's
        status, so a tmux session retained after a merge is still attachable.
        """
        entry = self.pull_request(ref)
        if entry is None or state not in PR_STATES:
            return None
        entry.state = state
        return entry

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
