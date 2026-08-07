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
from typing import List, Optional, Sequence

from .. import eventlog
from ..authz import is_authorized, is_self_authored
from ..sessions import DEFAULT_GITHUB_HOST, WorkItemRef, host_from_url

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
    """

    def __init__(self, maxsize: int = 1024):
        self.maxsize = max(1, maxsize)
        self._seen: "OrderedDict[str, None]" = OrderedDict()

    def __contains__(self, delivery_id: str) -> bool:
        return delivery_id in self._seen

    def add(self, delivery_id: str) -> None:
        self._seen[delivery_id] = None
        self._seen.move_to_end(delivery_id)
        while len(self._seen) > self.maxsize:
            self._seen.popitem(last=False)

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
    return None


def linked_issue_numbers(entity: dict, owner: str, repo: str) -> List[int]:
    """Issues a PR-shaped ``entity`` is linked to, most authoritative first.

    Three sources, deduplicated in order (issue-93):

    1. ``closingIssuesReferences`` — GitHub's *own* linkage (the Development
       panel as well as the keywords it parses). Present on the poll path, which
       asks ``gh`` for it; absent from webhook payloads, hence 2 and 3.
    2. the head branch's ``issue-<n>`` convention (the-loop's own branches);
    3. closing keywords in the PR body, in every form GitHub accepts.

    A qualified reference naming a **different** repository is ignored, as is a
    reference to the entity itself.
    """
    numbers: List[int] = []
    this_repo = f"{owner}/{repo}".lower()
    own_number = entity.get("number")

    def add(number: Optional[int]) -> None:
        if number is None or number == own_number or number in numbers:
            return
        numbers.append(number)

    for reference in entity.get("closingIssuesReferences") or []:
        number = (reference or {}).get("number")
        if isinstance(number, int):
            add(number)
    add(_issue_from_branch((entity.get("head") or {}).get("ref") or ""))
    for match in _CLOSING_KEYWORD_RE.finditer(entity.get("body") or ""):
        qualifier = match.group("url_repo") or match.group("repo")
        if qualifier and qualifier.lower() != this_repo:
            continue  # a closing reference to another repository is not ours
        raw = match.group("url_number") or match.group("number") or match.group("gh")
        add(int(raw))
    return numbers


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


def extract_work_items(event: str, payload: dict) -> List[WorkItemRef]:
    """Map a GitHub event payload to the work item(s) it concerns (R3.1).

    A PR event yields the issue(s) the PR is **linked** to *before* the PR's own
    number (issue-93): the linked issue is the work item the PR delivers, so a
    session registered against it is the one that must receive the event, and an
    unmatched event spawns against it rather than against the PR. A PR linked to
    no issue still routes as its own work item (non-GitHub ticketing).
    """
    parts = _repo_parts(payload)
    if parts is None:
        return []
    owner, repo = parts
    numbers: List[int] = []

    def add(number: Optional[int]) -> None:
        if number is not None and number not in numbers:
            numbers.append(number)

    pr = _pr_entity(event, payload)
    if pr is not None:
        for number in linked_issue_numbers(pr, owner, repo):
            add(number)
        add(pr.get("number"))
    elif event in ("issues", "issue_comment"):
        add((payload.get("issue") or {}).get("number"))
    elif event in ("workflow_run", "check_run", "check_suite", "status"):
        if event == "workflow_run":
            run = payload.get("workflow_run") or {}
        elif event == "check_run":
            run = (payload.get("check_run") or {}).get("check_suite") or {}
        elif event == "check_suite":
            run = payload.get("check_suite") or {}
        else:  # status events carry branch names only
            run = {}
        for pr in run.get("pull_requests") or []:
            add(pr.get("number"))
        add(_issue_from_branch(run.get("head_branch") or ""))
        for branch in payload.get("branches") or []:
            add(_issue_from_branch(branch.get("name") or ""))

    host = _host(payload)
    return [
        WorkItemRef(provider="github", owner=owner, repo=repo, number=n, host=host)
        for n in numbers
    ]


class Router:
    """Filter (R3.5) + dedup check (R3.4) + work-item extraction (R3.1)."""

    def __init__(
        self,
        events: Sequence[str] = (),
        dedup_size: int = 1024,
        deduper: Optional[Deduper] = None,
        auto_execute_label: str = "",
        authorized_users: Sequence[str] = (),
    ):
        self.events = list(events)
        self.auto_execute_label = auto_execute_label
        # Prompt-injection guard: only these logins' actions are actionable
        # (empty => fail closed for human-authored events). See the_loop.authz.
        self.authorized_users = list(authorized_users)
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
        if not is_lifecycle_close and not is_authorized(actor, self.authorized_users):
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
