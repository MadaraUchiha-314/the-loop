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

from ..sessions import WorkItemRef

logger = logging.getLogger("the-loop.gh-webhook")

# Branch naming conventions that link a branch to an issue, e.g.
# claude/github-issue-15-zkhlhh or feature/issue-15.
_BRANCH_ISSUE_RE = re.compile(r"issue[-/](\d+)", re.IGNORECASE)

# GitHub closing keywords in a PR body: "Closes #15", "fixes #7", "resolved #9".
_CLOSING_KEYWORD_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE
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


def _issue_from_branch(branch: str) -> Optional[int]:
    match = _BRANCH_ISSUE_RE.search(branch or "")
    return int(match.group(1)) if match else None


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


def extract_work_items(event: str, payload: dict) -> List[WorkItemRef]:
    """Map a GitHub event payload to the work item(s) it concerns (R3.1).

    A PR event also yields the issue its head branch / closing keywords point
    at, so a session registered against the *issue* receives its PR's events.
    """
    parts = _repo_parts(payload)
    if parts is None:
        return []
    owner, repo = parts
    numbers: List[int] = []

    def add(number: Optional[int]) -> None:
        if number is not None and number not in numbers:
            numbers.append(number)

    if event in ("issues", "issue_comment"):
        add((payload.get("issue") or {}).get("number"))
    elif event.startswith("pull_request"):
        pr = payload.get("pull_request") or {}
        add(pr.get("number"))
        add(_issue_from_branch((pr.get("head") or {}).get("ref") or ""))
        for match in _CLOSING_KEYWORD_RE.finditer(pr.get("body") or ""):
            add(int(match.group(1)))
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

    return [
        WorkItemRef(provider="github", owner=owner, repo=repo, number=n)
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
    ):
        self.events = list(events)
        self.auto_execute_label = auto_execute_label
        # Share the dispatcher's deduper so the router's early duplicate check
        # sees the ids the dispatcher marks as processed.
        self.deduper = deduper if deduper is not None else Deduper(maxsize=dedup_size)

    def route(
        self, event: str, payload: dict, delivery_id: str
    ) -> Optional[RoutedEvent]:
        """Return a RoutedEvent, or None when filtered / duplicate / unmappable."""
        if self.events and event not in self.events:
            logger.debug("ignoring disabled event type %s", event)
            return None
        if delivery_id and delivery_id in self.deduper:
            logger.info("duplicate delivery %s ignored (already seen)", delivery_id)
            return None
        work_items = extract_work_items(event, payload)
        if not work_items:
            logger.debug("event %s maps to no work item; ignoring", event)
            return None
        return RoutedEvent(
            event=event,
            action=str(payload.get("action") or ""),
            delivery_id=delivery_id or "",
            work_items=work_items,
            payload=payload,
            labeled=event_carries_label(payload, self.auto_execute_label),
        )
