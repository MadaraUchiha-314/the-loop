"""The event catalog — one table every channel subscribes to and publishes from.

Since issue-309 (decision-103) everything the-loop says and hears is an event with a
type from this table, and the table answers four questions per type:

* what it means (``description`` — printed by ``the-loop channels status`` and the
  configuration reference, pinned together by a test so the three cannot drift);
* whether a channel MAY **subscribe** to it (``channels.<name>.subscribe``);
* whether a channel MAY **publish** it (``channels.<name>.publish`` — a grant: what a
  message on that channel may *become*);
* whether the **ledger records** it when it originates off the ledger (a comment with
  a machine-readable envelope, or the issue itself for ``work-item.create``).

Unknown names are warned about, **not** refused, on the subscribe side: a custom
process graph may fire a custom ``notify`` event, and an allow-list entry for it must
keep working. On the publish side an unknown or non-publishable name is warned about
and **ignored** — a typo must never widen what a chat message may do.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

__all__ = [
    "EVENTS",
    "EventSpec",
    "NOTIFICATION_EVENTS",
    "PUBLISHABLE_EVENTS",
    "SUBSCRIBABLE_EVENTS",
    "APPROVAL_EVENTS",
    "is_recorded",
]


@dataclass(frozen=True)
class EventSpec:
    """One row of the catalog."""

    description: str
    origin: str = "loop"  # loop | cli | github | channel
    subscribable: bool = True
    publishable: bool = False
    recorded: bool = False


#: The graph notification vocabulary (harness config `notifications.events`).
NOTIFICATION_EVENTS: Tuple[str, ...] = (
    "decision-pending",
    "phase-approval-pending",
    "pr-review-pending",
    "security-sign-off-pending",
    "conflict-escalated",
    "work-item-complete",
)

#: The notifications a human answers with an approval — where a Slack message may
#: carry Approve / Request changes buttons (R4.3).
APPROVAL_EVENTS: Tuple[str, ...] = (
    "phase-approval-pending",
    "pr-review-pending",
    "security-sign-off-pending",
)

EVENTS: Dict[str, EventSpec] = {
    "session.awaiting_input": EventSpec(
        "An agent asked a human a question (`the-loop ask`) and is waiting — "
        "the conversation starter, and the default subscription.",
        origin="cli",
        recorded=True,  # its record IS the question comment
    ),
    "decision-pending": EventSpec(
        "The graph reached a point where a human decision or opinion is "
        "genuinely required."
    ),
    "phase-approval-pending": EventSpec(
        "A spec-chain phase (requirements, design + testing plan, tasks) is "
        "ready for its human gate."
    ),
    "pr-review-pending": EventSpec(
        "A pull request delivering the work item is ready for human review."
    ),
    "security-sign-off-pending": EventSpec(
        "The work item's risk tier requires a named human security sign-off."
    ),
    "conflict-escalated": EventSpec(
        "The loop hit a genuine block, logged the conflict and escalated once."
    ),
    "work-item-complete": EventSpec("The work item reached `complete`."),
    "comment.agent": EventSpec(
        "The agent's own comment on the work item (marker-stamped) — the "
        "requirements summary, the phase checklist, a review note.",
        origin="github",
    ),
    "comment.human": EventSpec(
        "A human's comment the ledger accepted — an authorized user's, or a "
        "work-item collaborator's.",
        origin="github",
    ),
    "work-item.reply": EventSpec(
        "A message on a channel, delivered into the waiting session as input — "
        "the default grant, and today's behaviour.",
        origin="channel",
        subscribable=False,
        publishable=True,
        recorded=True,
    ),
    "gate.feedback": EventSpec(
        "A message on a channel that answers an open human gate — recorded on "
        "the ledger unmarked, so the ledger's ingress classifies it.",
        origin="channel",
        subscribable=False,
        publishable=True,
        recorded=True,
    ),
    "control.command": EventSpec(
        "A control keyword typed on a channel — recorded on the ledger "
        "unmarked, so the ledger's ingress executes it through the control seam.",
        origin="channel",
        subscribable=False,
        publishable=True,
        recorded=True,
    ),
    "work-item.create": EventSpec(
        "A top-level message on a channel that opens a work item — the record "
        "is the issue, created in `kickoff.repo` with `kickoff.labels`.",
        origin="channel",
        subscribable=False,
        publishable=True,
        recorded=True,
    ),
    "standing.started": EventSpec(
        "A standing session (issue-277) came up and opened its thread — no "
        "ticket, so nothing to record.",
        origin="loop",
    ),
}

#: name → description of every event a channel may subscribe to (the shape the
#: config parser, `channels status` and the docs pin have read since PR #267).
SUBSCRIBABLE_EVENTS: Dict[str, str] = {
    name: spec.description for name, spec in EVENTS.items() if spec.subscribable
}

#: The grants: what a message on a channel may become.
PUBLISHABLE_EVENTS: Tuple[str, ...] = tuple(
    name for name, spec in EVENTS.items() if spec.publishable
)


def is_recorded(event_type: str) -> bool:
    """Whether the ledger writes ``event_type`` down when it originates elsewhere.

    Unknown types are not recorded: a custom notify event is a notification, and the
    graph's own hooks already post whatever comment it needs.
    """
    spec = EVENTS.get(event_type)
    return bool(spec and spec.recorded)
