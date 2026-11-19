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

from .. import strings

__all__ = [
    "EVENTS",
    "EventSpec",
    "LIFECYCLE_EVENTS",
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


#: The graph notification vocabulary — the events the graph's `notify` hook publishes
#: (until issue-352 also the harness config's `notifications.events` taxonomy).
NOTIFICATION_EVENTS: Tuple[str, ...] = (
    "decision-pending",
    "phase-approval-pending",
    "pr-review-pending",
    "security-sign-off-pending",
    "conflict-escalated",
    "work-item-complete",
)

#: The lifecycle a work item's loop publishes on its own (issue-378): the runtime
#: fires the two phase events on every walk of every graph — following the
#: `loop:<phase>` label, so two nodes sharing a phase publish nothing between
#: them — and the dispatcher fires the closure when the ledger says the item
#: ended. None is recorded: the label and the closure ARE the ledger's record.
LIFECYCLE_EVENTS: Tuple[str, ...] = (
    "phase.started",
    "phase.completed",
    "work-item.closed",
)

#: The notifications a human answers with an approval — where a Slack message may
#: carry Approve / Request changes buttons (R4.3).
APPROVAL_EVENTS: Tuple[str, ...] = (
    "phase-approval-pending",
    "pr-review-pending",
    "security-sign-off-pending",
)

#: What each event means, in words (`channels status`, the docs pin).
_DESCRIPTIONS: Dict[str, str] = strings.section("channels.events.description")

EVENTS: Dict[str, EventSpec] = {
    "session.awaiting_input": EventSpec(
        _DESCRIPTIONS["session.awaiting_input"],
        origin="cli",
        recorded=True,  # its record IS the question comment
    ),
    "decision-pending": EventSpec(_DESCRIPTIONS["decision-pending"]),
    "phase-approval-pending": EventSpec(_DESCRIPTIONS["phase-approval-pending"]),
    "pr-review-pending": EventSpec(_DESCRIPTIONS["pr-review-pending"]),
    "security-sign-off-pending": EventSpec(_DESCRIPTIONS["security-sign-off-pending"]),
    "conflict-escalated": EventSpec(_DESCRIPTIONS["conflict-escalated"]),
    "work-item-complete": EventSpec(_DESCRIPTIONS["work-item-complete"]),
    "phase.started": EventSpec(_DESCRIPTIONS["phase.started"]),
    "phase.completed": EventSpec(_DESCRIPTIONS["phase.completed"]),
    "phase.progress": EventSpec(_DESCRIPTIONS["phase.progress"]),
    "work-item.closed": EventSpec(_DESCRIPTIONS["work-item.closed"]),
    "comment.agent": EventSpec(
        _DESCRIPTIONS["comment.agent"],
        origin="github",
    ),
    "comment.human": EventSpec(
        _DESCRIPTIONS["comment.human"],
        origin="github",
    ),
    "work-item.reply": EventSpec(
        _DESCRIPTIONS["work-item.reply"],
        origin="channel",
        subscribable=False,
        publishable=True,
        recorded=True,
    ),
    "gate.feedback": EventSpec(
        _DESCRIPTIONS["gate.feedback"],
        origin="channel",
        subscribable=False,
        publishable=True,
        recorded=True,
    ),
    "control.command": EventSpec(
        _DESCRIPTIONS["control.command"],
        origin="channel",
        subscribable=False,
        publishable=True,
        recorded=True,
    ),
    "work-item.create": EventSpec(
        _DESCRIPTIONS["work-item.create"],
        origin="channel",
        subscribable=False,
        publishable=True,
        recorded=True,
    ),
    # The two acts a mention asks for (issue-389, decision-133 D4/D5): each is
    # recorded on the ticket as a MARKED, enveloped comment — so no gate ever
    # reads a decision as an approval — and delivered by the channel itself into
    # the session with a preset frame. Grants, not subscriptions: what a message
    # may BECOME; a channel that wants to hear one subscribes to `comment.agent`.
    "context.added": EventSpec(
        _DESCRIPTIONS["context.added"],
        origin="channel",
        subscribable=False,
        publishable=True,
        recorded=True,
    ),
    "decision.recorded": EventSpec(
        _DESCRIPTIONS["decision.recorded"],
        origin="channel",
        subscribable=False,
        publishable=True,
        recorded=True,
    ),
    "standing.started": EventSpec(
        _DESCRIPTIONS["standing.started"],
        origin="loop",
    ),
    # The two grants a `/the-loop` slash command needs beyond `control.command`
    # (issue-334, decision-116 D3). Publishable, not subscribable, and NOT
    # recorded: there is no ticket to record on, so the event log is their
    # paper trail — as it is for a standing session's reply (issue-277).
    "instance.command": EventSpec(
        _DESCRIPTIONS["instance.command"],
        origin="channel",
        subscribable=False,
        publishable=True,
        recorded=False,
    ),
    "standing.command": EventSpec(
        _DESCRIPTIONS["standing.command"],
        origin="channel",
        subscribable=False,
        publishable=True,
        recorded=False,
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
