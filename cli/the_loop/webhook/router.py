"""Route GitHub webhook events to work items: filter, dedup, extract refs.

Pure functions from ``(event_name, payload)`` to routing decisions — no I/O —
so extraction is unit-testable per event type. Stdlib only.

Spec: docs/specs/issue-15/design.md §2 (requirement R3).
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, List, Optional, Sequence, Set, Tuple

from .. import eventlog
from ..authz import is_authorized, is_self_authored
from ..sessions import DEFAULT_GITHUB_HOST, WorkItemRef, host_from_url

if TYPE_CHECKING:  # the roster is injected, never built here (issue-307)
    from ..collaborators import CollaboratorStore

logger = logging.getLogger("the-loop.gh-webhook")

# Branch naming conventions that link a branch to an issue, e.g.
# claude/github-issue-15-zkhlhh or feature/issue-15.
_BRANCH_ISSUE_RE = re.compile(r"issue[-/](\d+)", re.IGNORECASE)

# GitHub closing keywords in a PR body, in every form GitHub itself accepts
# (issue-93): "Closes #15", "Fixes: #15", "Closes octo/repo#15", "Resolved
# GH-15", "fix https://github.com/octo/repo/issues/15". The URL alternative
# comes first so a full link is not half-matched by the "#" one. A qualified
# reference (``url_repo``/``repo``) naming another repository is dropped by
# :func:`linked_issue_numbers` rather than read as this repo's issue number.
_CLOSING_KEYWORD_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s+"
    r"(?:"
    r"https?://[^\s/]+/(?P<url_repo>[\w.-]+/[\w.-]+)/issues/(?P<url_number>\d+)"
    r"|(?P<repo>[\w.-]+/[\w.-]+)?#(?P<number>\d+)"
    r"|GH-(?P<gh>\d+)"
    r")",
    re.IGNORECASE,
)

#: Where a work-item ref came from (issue-269). Provenance is not decoration: of
#: the four, exactly one — ``SOURCE_BRANCH`` — supplies a repository the event
#: never stated, so it is the only one that can name a work item nobody created.
SOURCE_REFERENCE = "closing-reference"  # GitHub's own closingIssuesReferences
SOURCE_BRANCH = "branch"  # the issue-<n> head-branch / CI-branch convention
SOURCE_KEYWORD = "keyword"  # a closing keyword in the pull request's body
SOURCE_ENTITY = "entity"  # the issue/PR the event is about (GitHub said so)


@dataclass
class RoutedEvent:
    """A verified, filtered, deduplicated event ready for dispatch."""

    event: str
    action: str
    delivery_id: str
    work_items: List[WorkItemRef]
    payload: dict = field(repr=False, default_factory=dict)
    # True when the event's issue/PR carries the configured auto-execute label
    # (or is the label being added right now). Gates label-driven spawning.
    labeled: bool = False


class Deduper:
    """Bounded LRU of processed delivery ids (at-most-once, R3.4).

    GitHub redelivery is the at-least-once retry path: a failed dispatch is
    ``discard``-ed again so its redelivery gets through.

    Each entry also carries that delivery's **outcome** (issue-270): empty while
    it is in play, and one of the dispatcher's fixed literals once the dispatcher
    is *finished* with it — suppressed on purpose, or consumed as a control
    command. A marked id used to mean only "seen", which the poll path could not
    tell apart from "still on its way", so it kept a refused comment at
    ``commentAttempts: 1`` forever. The outcome lives in this entry rather than a
    second cache so one eviction, one :meth:`discard` and one ``dedupCacheSize``
    govern both; a parallel store could disagree with this one about which ids
    are known, which is the class of bug being fixed.
    """

    def __init__(self, maxsize: int = 1024):
        self.maxsize = max(1, maxsize)
        self._seen: "OrderedDict[str, str]" = OrderedDict()

    def __contains__(self, delivery_id: str) -> bool:
        return delivery_id in self._seen

    def add(self, delivery_id: str, outcome: str = "") -> None:
        self._seen[delivery_id] = outcome
        self._seen.move_to_end(delivery_id)
        while len(self._seen) > self.maxsize:
            self._seen.popitem(last=False)

    def mark_settled(self, delivery_id: str, outcome: str) -> None:
        """Record that nothing more is coming for ``delivery_id``.

        Marks an id this cache never held: every settling site keeps the delivery
        id on purpose, which is exactly what "not discarded" already meant.
        """
        self.add(delivery_id, outcome=outcome)

    def outcome(self, delivery_id: str) -> str:
        """``""`` for an unmarked or still-in-play delivery, else its outcome."""
        return self._seen.get(delivery_id) or ""

    def discard(self, delivery_id: str) -> None:
        self._seen.pop(delivery_id, None)


def _repo_parts(payload: dict) -> Optional[tuple]:
    full_name = (payload.get("repository") or {}).get("full_name") or ""
    owner, sep, repo = full_name.partition("/")
    if not sep:
        return None
    return owner, repo


def _host(payload: dict) -> str:
    """Which GitHub the event came from, read off the payload (issue-130 review).

    The repository's ``html_url`` is the authority — every real webhook carries
    it. The poller's synthesised payloads carry the *item's* URL instead, so that
    is the fallback, and both give a GitHub Enterprise work item a ref that says
    so. Neither present (a hand-written payload, an older fixture) means
    github.com, which is what a ref without a host has always meant.
    """
    repo_url = str((payload.get("repository") or {}).get("html_url") or "")
    if repo_url:
        return host_from_url(repo_url)
    for key in ("issue", "pull_request"):
        entity_url = str((payload.get(key) or {}).get("html_url") or "")
        if entity_url:
            return host_from_url(entity_url)
    return DEFAULT_GITHUB_HOST


def _issue_from_branch(branch: str) -> Optional[int]:
    match = _BRANCH_ISSUE_RE.search(branch or "")
    return int(match.group(1)) if match else None


def _pr_entity(event: str, payload: dict) -> Optional[dict]:
    """The pull-request-shaped entity this event concerns, or ``None`` (issue-93).

    GitHub delivers a PR **conversation comment** as ``issue_comment`` whose
    ``issue`` object carries a ``pull_request`` key — so an event naming an
    "issue" is not necessarily about an issue. That entity still carries the
    PR's ``number``, ``body`` (the PR description) and ``labels``, which is what
    linked-issue resolution needs; only ``head`` is absent there.
    """
    if event.startswith("pull_request"):
        return payload.get("pull_request") or None
    if event in ("issues", "issue_comment"):
        issue = payload.get("issue") or {}
        if issue.get("pull_request"):
            return issue
        # The POLL path synthesises a comment event over the pull request's own
        # payload — key ``pull_request``, head branch and all — and renames the
        # event to ``issue_comment`` (issue-269). Reading only ``issue`` there
        # answered "this event carries no pull request" for every polled comment:
        # no binding was recorded and no endpoint was ever chosen for one. No
        # real webhook puts a ``pull_request`` beside an ``issue_comment``, so
        # this fallback is unreachable on that path.
        return payload.get("pull_request") or None
    return None


def _reference_repo(reference: dict, owner: str, repo: str) -> Tuple[str, str]:
    """The ``(owner, repo)`` a ``closingIssuesReferences`` entry belongs to.

    ``gh`` returns the entry's repository in more than one shape depending on the
    query, and a webhook payload omits it entirely — so the event's own
    repository is the fallback, which is what every entry meant before
    cross-repo links were read at all (issue-183).
    """
    repository = reference.get("repository")
    if isinstance(repository, dict):
        name_with_owner = str(repository.get("nameWithOwner") or "")
        if name_with_owner.count("/") == 1:
            left, right = name_with_owner.split("/")
            if left and right:
                return left, right
        holder = repository.get("owner")
        name = str(repository.get("name") or "")
        login = str(holder.get("login") or "") if isinstance(holder, dict) else ""
        if login and name:
            return login, name
    url = str(reference.get("url") or "")
    match = re.search(r"/([\w.-]+)/([\w.-]+)/issues/\d+", url)
    if match:
        return match.group(1), match.group(2)
    return owner, repo


def linked_work_item_sources(
    entity: dict, owner: str, repo: str, host: str = ""
) -> "OrderedDict[str, Tuple[WorkItemRef, Set[str]]]":
    """The traversal :func:`linked_work_items` renders, with each ref's sources.

    One walk, two readers (issue-269). The list of refs was always the answer to
    "which work items?"; this is the answer to "and how do we know?" — needed
    because :data:`SOURCE_BRANCH` is the only source that supplies a repository
    the pull request never stated, and therefore the only one that can name a
    work item nobody created. A ref reachable through more than one source
    carries all of them, so corroboration is visible rather than lost to
    first-wins deduplication.

    Keyed on :attr:`WorkItemRef.ref`, insertion-ordered most authoritative first
    — the order :func:`linked_work_items` has always returned.
    """
    items: "OrderedDict[str, Tuple[WorkItemRef, Set[str]]]" = OrderedDict()
    own_number = entity.get("number")

    def add(
        number: Optional[int], source: str, in_owner: str = "", in_repo: str = ""
    ) -> None:
        if number is None:
            return
        target_owner, target_repo = in_owner or owner, in_repo or repo
        local = target_owner.lower() == owner.lower() and target_repo.lower() == (
            repo.lower()
        )
        if local and number == own_number:
            return
        ref = WorkItemRef(
            provider="github",
            owner=target_owner,
            repo=target_repo,
            number=number,
            host=host,
        )
        known = items.get(ref.ref)
        if known is None:
            items[ref.ref] = (ref, {source})
        else:
            known[1].add(source)

    for reference in entity.get("closingIssuesReferences") or []:
        reference = reference or {}
        number = reference.get("number")
        if isinstance(number, int):
            add(number, SOURCE_REFERENCE, *_reference_repo(reference, owner, repo))
    add(_issue_from_branch((entity.get("head") or {}).get("ref") or ""), SOURCE_BRANCH)
    for match in _CLOSING_KEYWORD_RE.finditer(entity.get("body") or ""):
        qualifier = match.group("url_repo") or match.group("repo")
        raw = match.group("url_number") or match.group("number") or match.group("gh")
        if qualifier and qualifier.count("/") == 1:
            other_owner, other_repo = qualifier.split("/")
            add(int(raw), SOURCE_KEYWORD, other_owner, other_repo)
        else:
            add(int(raw), SOURCE_KEYWORD)
    return items


def linked_work_items(
    entity: dict, owner: str, repo: str, host: str = ""
) -> List[WorkItemRef]:
    """Work items a PR-shaped ``entity`` is linked to, most authoritative first.

    Three sources, deduplicated in order (issue-93):

    1. ``closingIssuesReferences`` — GitHub's *own* linkage (the Development
       panel as well as the keywords it parses). Present on the poll path, which
       asks ``gh`` for it; absent from webhook payloads, hence 2 and 3.
    2. the head branch's ``issue-<n>`` convention (the-loop's own branches);
    3. closing keywords in the PR body, in every form GitHub accepts.

    A reference to the entity itself is ignored. A **qualified** reference naming
    another repository is honoured (issue-183): a work item may need
    contributions in several repositories, and the pull request that delivers one
    of them lives in that repository while the ticket lives in the origin
    repository. It is returned as a ref *in the repository it names* — the whole
    reason this returns refs rather than numbers, which cannot say where they
    belong. The branch convention stays local: ``issue-12`` on a branch says
    nothing about a repository — and says nothing about *existence* either, which
    is why the ref it produces is checked before it is acted on (issue-269; the
    provenance is :func:`linked_work_item_sources`).

    Nothing here widens which events *reach* the router — that is the operator's
    receiver and poll sources — nor which work items are armed. It widens only
    which work item an event that already arrived is about.
    """
    return [
        item for item, _ in linked_work_item_sources(entity, owner, repo, host).values()
    ]


def linked_issue_numbers(entity: dict, owner: str, repo: str) -> List[int]:
    """The same linkage, narrowed to issues in **this** repository.

    Kept as the numbers-only view for callers that cannot act on another
    repository's work item; :func:`linked_work_items` is the full answer.
    """
    return [
        item.number
        for item in linked_work_items(entity, owner, repo)
        if item.owner.lower() == owner.lower() and item.repo.lower() == repo.lower()
    ]


def pr_work_item(event: str, payload: dict) -> Optional[WorkItemRef]:
    """The pull request's **own** ref for an event that concerns one (issue-172).

    ``None`` for everything else — an issue event, a CI event, a payload naming
    no repository. Composed from the same three helpers
    :func:`extract_work_items` uses, so the ref returned here is exactly the one
    that function emits *last*; the two cannot drift into disagreeing about which
    PR an event is about.

    The dispatcher needs this to name the ref a durable binding is written under.
    Deliberately not folded into :class:`RoutedEvent`: routing stays a pure
    payload → work-items mapping, and only the one caller that persists a binding
    pays for the extra parse.
    """
    parts = _repo_parts(payload)
    if parts is None:
        return None
    entity = _pr_entity(event, payload)
    number = (entity or {}).get("number")
    if not isinstance(number, int):
        return None
    owner, repo = parts
    return WorkItemRef(
        provider="github", owner=owner, repo=repo, number=number, host=_host(payload)
    )


def event_carries_label(payload: dict, label: str) -> bool:
    """True if this event's issue/PR carries ``label`` (or is adding it now).

    Reads labels straight from the webhook payload (no GitHub API call), so
    label-gating keeps the zero-dependency guarantee. Matches either the label
    being added in a ``labeled`` action or the item's current label set.
    """
    if not label:
        return False
    if payload.get("action") == "labeled":
        if ((payload.get("label") or {}).get("name")) == label:
            return True
    for key in ("issue", "pull_request"):
        for lab in (payload.get(key) or {}).get("labels") or []:
            if (lab or {}).get("name") == label:
                return True
    return False


def event_actor(event: str, payload: dict) -> Optional[str]:
    """The human GitHub login responsible for this event, or ``None``.

    Content/action events resolve to their author/actor (the prompt-injection
    surface); pure system events (CI ``workflow_run``/``check_*``/``status``)
    resolve to ``None`` — they carry status, not free-form instructions.
    """
    if event in ("issue_comment", "pull_request_review_comment"):
        return ((payload.get("comment") or {}).get("user") or {}).get("login")
    if event == "pull_request_review":
        return ((payload.get("review") or {}).get("user") or {}).get("login")
    if event == "issues" or event.startswith("pull_request"):
        return (payload.get("sender") or {}).get("login")
    return None


def event_body(event: str, payload: dict) -> Optional[str]:
    """The free-form text this event carries, or ``None`` (issue-64).

    Only content-bearing events have a body worth marker-checking; the caller
    uses this to recognize (and drop) the-loop's own replies before they can
    re-enter the loop. Pure system events and label/open actions return
    ``None`` — they carry no reply text to check.
    """
    if event in ("issue_comment", "pull_request_review_comment"):
        return (payload.get("comment") or {}).get("body")
    if event == "pull_request_review":
        return (payload.get("review") or {}).get("body")
    return None


def work_item_sources(
    event: str, payload: dict
) -> "OrderedDict[str, Tuple[WorkItemRef, Set[str]]]":
    """:func:`extract_work_items` with each ref's provenance (issue-269).

    The one traversal; :func:`extract_work_items` and :func:`branch_derived_refs`
    are views over it, so the refs an event yields and the story of where they
    came from cannot drift apart.
    """
    parts = _repo_parts(payload)
    if parts is None:
        return OrderedDict()
    owner, repo = parts
    host = _host(payload)
    items: "OrderedDict[str, Tuple[WorkItemRef, Set[str]]]" = OrderedDict()

    def add_ref(ref: WorkItemRef, source: str) -> None:
        known = items.get(ref.ref)
        if known is None:
            items[ref.ref] = (ref, {source})
        else:
            known[1].add(source)

    def add(number: Optional[int], source: str) -> None:
        if number is None:
            return
        add_ref(
            WorkItemRef(
                provider="github", owner=owner, repo=repo, number=number, host=host
            ),
            source,
        )

    pr = _pr_entity(event, payload)
    if pr is not None:
        # A PR's linked work items may live in ANOTHER repository (issue-183),
        # so they are carried as refs; everything else here is a number in the
        # event's own repository.
        for item, sources in linked_work_item_sources(pr, owner, repo, host).values():
            for source in sources:
                add_ref(item, source)
        add(pr.get("number"), SOURCE_ENTITY)
    elif event in ("issues", "issue_comment"):
        add((payload.get("issue") or {}).get("number"), SOURCE_ENTITY)
    elif event in ("workflow_run", "check_run", "check_suite", "status"):
        if event == "workflow_run":
            run = payload.get("workflow_run") or {}
        elif event == "check_run":
            run = (payload.get("check_run") or {}).get("check_suite") or {}
        elif event == "check_suite":
            run = payload.get("check_suite") or {}
        else:  # status events carry branch names only
            run = {}
        for linked_pr in run.get("pull_requests") or []:
            add(linked_pr.get("number"), SOURCE_ENTITY)
        add(_issue_from_branch(run.get("head_branch") or ""), SOURCE_BRANCH)
        for branch in payload.get("branches") or []:
            add(_issue_from_branch(branch.get("name") or ""), SOURCE_BRANCH)
    return items


def extract_work_items(event: str, payload: dict) -> List[WorkItemRef]:
    """Map a GitHub event payload to the work item(s) it concerns (R3.1).

    A PR event yields the issue(s) the PR is **linked** to *before* the PR's own
    number (issue-93): the linked issue is the work item the PR delivers, so a
    session registered against it is the one that must receive the event, and an
    unmatched event spawns against it rather than against the PR. A PR linked to
    no issue still routes as its own work item (non-GitHub ticketing).
    """
    return [item for item, _ in work_item_sources(event, payload).values()]


def branch_derived_refs(event: str, payload: dict) -> List[str]:
    """The refs this event yields **only** through the branch convention (issue-269).

    The weakest linkage there is, and the one that cannot be wrong quietly: a
    branch says ``issue-285`` and the ref is resolved in the event's own
    repository, which may have no issue 285 at all. Everything else states its
    repository — GitHub's own reference, or a qualified closing keyword — or
    *is* the entity GitHub delivered the event about.

    Names refs, not items: the dispatcher matches these against the refs it is
    about to act on, and a ref string is the identity both sides already use.
    """
    return [
        ref
        for ref, (_, sources) in work_item_sources(event, payload).items()
        if sources == {SOURCE_BRANCH}
    ]


#: The events that carry a comment body, and the payload object it sits in.
_COMMENT_EVENTS = {
    "issue_comment": "comment",
    "pull_request_review_comment": "comment",
    "pull_request_review": "review",
}


class Router:
    """Filter (R3.5) + dedup check (R3.4) + work-item extraction (R3.1)."""

    def __init__(
        self,
        events: Sequence[str] = (),
        dedup_size: int = 1024,
        deduper: Optional[Deduper] = None,
        auto_execute_label: str = "",
        authorized_users: Sequence[str] = (),
        collaborators: Optional["CollaboratorStore"] = None,
        publisher: Optional[Callable[[str, str, str, str, str], None]] = None,
    ):
        self.events = list(events)
        self.auto_execute_label = auto_execute_label
        # The bus (issue-309): a comment this ingress drops as the agent's own, or
        # accepts as a human's, is published to the subscribed channels —
        # `comment.agent` / `comment.human`. Injected, so a router built without
        # one (tests, embedders) publishes nothing and knows no config.
        self.publisher = publisher
        # Prompt-injection guard: only these logins' actions are actionable
        # (empty => fail closed for human-authored events). See the_loop.authz.
        self.authorized_users = list(authorized_users)
        # The second, narrower allow-list (issue-307): per work item, and injected
        # rather than constructed, so the router keeps knowing nothing about where
        # state lives. ``None`` means "no rosters" — a router built without one
        # behaves exactly as it did before work-item collaborators existed.
        self.collaborators = collaborators
        # Share the dispatcher's deduper so the router's early duplicate check
        # sees the ids the dispatcher marks as processed.
        self.deduper = deduper if deduper is not None else Deduper(maxsize=dedup_size)

    def route(
        self, event: str, payload: dict, delivery_id: str
    ) -> Optional[RoutedEvent]:
        """Return a RoutedEvent, or None when filtered / duplicate / unmappable."""
        action = str(payload.get("action") or "")
        if self.events and event not in self.events:
            logger.debug("ignoring disabled event type %s", event)
            eventlog.emit(
                "routing.dropped",
                level="debug",
                reason="disabled-event",
                gh_event=event,
                action=action,
                delivery_id=delivery_id,
            )
            return None
        if delivery_id and delivery_id in self.deduper:
            logger.info("duplicate delivery %s ignored (already seen)", delivery_id)
            eventlog.emit(
                "routing.dropped",
                reason="duplicate-delivery",
                gh_event=event,
                action=action,
                delivery_id=delivery_id,
            )
            return None
        work_items = extract_work_items(event, payload)
        if not work_items:
            logger.debug("event %s maps to no work item; ignoring", event)
            eventlog.emit(
                "routing.dropped",
                level="debug",
                reason="no-work-item",
                gh_event=event,
                action=action,
                delivery_id=delivery_id,
            )
            return None
        # Self-reply guard (issue-64): the-loop's own replies are posted under
        # the operator's own credentials, so they would otherwise pass the
        # actor check below and re-enter the loop. Checked before authorization
        # so it applies regardless of who technically posted it.
        if is_self_authored(event_body(event, payload)):
            logger.debug("ignoring %s: the-loop's own reply (marker present)", event)
            self._publish("agent", event, payload, work_items)
            eventlog.emit(
                "routing.dropped",
                level="debug",
                reason="self-authored",
                gh_event=event,
                action=action,
                delivery_id=delivery_id,
                work_items=[w.ref for w in work_items],
            )
            return None
        # Authorization guard (prompt-injection remediation). Closing the work
        # item (a merged/closed PR, or — issue-94 — a closed issue) is a
        # lifecycle signal: it only auto-closes the-loop's own session and
        # injects nothing, so it bypasses the actor check to keep cleanup
        # working. The reverse direction stays guarded: a close can never spawn.
        is_lifecycle_close = event in ("issues", "pull_request") and (
            str(payload.get("action") or "") == "closed"
        )
        actor = event_actor(event, payload)
        # A work-item collaborator is the narrower answer to the same question
        # (issue-307): an authorized user granted this login the right to be *input*
        # on these work items. Only the refs THIS event named are consulted, which is
        # what keeps a grant on one work item from reaching another. What the grant
        # does not buy is checked further in: the control seam and the spawn seam
        # both re-check `authorizedUsers` for a named actor. Consulted only once the
        # allow-list has said no, so the ordinary path reads no rosters at all.
        authorized = is_lifecycle_close or is_authorized(actor, self.authorized_users)
        collaborator = (
            not authorized
            and bool(actor)
            and self.collaborators is not None
            and self.collaborators.permits(actor, work_items)
        )
        if not authorized and not collaborator:
            logger.warning(
                "ignoring %s for %s from unauthorized actor %r "
                "(not in routing.authorizedUsers)",
                event,
                ", ".join(w.ref for w in work_items),
                actor,
            )
            eventlog.emit(
                "routing.dropped",
                level="warning",
                reason="unauthorized-actor",
                gh_event=event,
                action=action,
                delivery_id=delivery_id,
                actor=actor,
                work_items=[w.ref for w in work_items],
            )
            return None
        if collaborator:  # implies the allow-list said no — so say what let it in
            logger.info(
                "routing %s for %s from %r, a collaborator on it: their comment is "
                "input for the session, and nothing more",
                event,
                ", ".join(w.ref for w in work_items),
                actor,
            )
            eventlog.emit(
                "routing.collaborator",
                gh_event=event,
                action=action,
                delivery_id=delivery_id,
                actor=actor,
                work_items=[w.ref for w in work_items],
            )
        if actor and not is_lifecycle_close:
            self._publish("human", event, payload, work_items)
        labeled = event_carries_label(payload, self.auto_execute_label)
        eventlog.emit(
            "routing.routed",
            gh_event=event,
            action=action,
            delivery_id=delivery_id,
            actor=actor,
            work_items=[w.ref for w in work_items],
            labeled=labeled,
        )
        return RoutedEvent(
            event=event,
            action=action,
            delivery_id=delivery_id or "",
            work_items=work_items,
            payload=payload,
            labeled=labeled,
        )

    def _publish(self, kind: str, event: str, payload: dict, work_items) -> None:
        """Hand a comment to the bus as ``comment.<kind>`` — best-effort, and only
        for the events that carry a comment body (a label or a CI event is not
        a comment). The first work item the event names is the one the comment
        sits on; a PR review's linked issue hears it through that binding."""
        if self.publisher is None or not work_items:
            return
        body = event_body(event, payload)
        if not body or event not in _COMMENT_EVENTS:
            return
        from ..channels.envelope import has_envelope

        if has_envelope(body):
            return  # the bus's own record (A10): its source channel has it
        container = _COMMENT_EVENTS[event]
        url = str((payload.get(container) or {}).get("html_url") or "")
        try:
            self.publisher(
                kind,
                work_items[0].ref,
                event_actor(event, payload) or "",
                str(body),
                url,
            )
        except Exception:  # noqa: BLE001 — the bus never touches ingress
            logger.exception("comment publisher raised for %s", event)
