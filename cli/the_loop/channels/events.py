"""The subscribable-event catalog — the common definition `channels.*.events`
configures against (owner's review call on PR #267).

One dict, three consumers: the config parser warns against it (a typo in an
allow-list otherwise fails *silently* — the event just never arrives),
`the-loop channels status` prints it with subscription ticks, and the docs
page lists it, pinned by a test so the two cannot drift.

The catalog is the union of what can actually reach a channel today:

* the **ask** (`session.awaiting_input`) — `the-loop ask`'s broadcast;
* the **graph notification events** — what the `notify` hook fires, named in
  the shipped process graphs and the harness config's `notifications.events`
  taxonomy (a test pins that containment, so a new notification event cannot
  ship without joining this catalog).

Unknown names are warned about, **not** refused: a custom process graph may
fire a custom `notify` event, and an allow-list entry for it must keep
working. The warning exists for the typo, not the pioneer.
"""

from __future__ import annotations

from typing import Dict, Tuple

__all__ = ["SUBSCRIBABLE_EVENTS", "NOTIFICATION_EVENTS"]

#: The graph notification vocabulary (harness config `notifications.events`).
NOTIFICATION_EVENTS: Tuple[str, ...] = (
    "decision-pending",
    "phase-approval-pending",
    "pr-review-pending",
    "security-sign-off-pending",
    "conflict-escalated",
    "work-item-complete",
)

SUBSCRIBABLE_EVENTS: Dict[str, str] = {
    "session.awaiting_input": (
        "An agent asked a human a question (`the-loop ask`) and is waiting — "
        "the conversation starter, and the default subscription."
    ),
    "decision-pending": (
        "The graph reached a point where a human decision or opinion is "
        "genuinely required."
    ),
    "phase-approval-pending": (
        "A spec-chain phase (requirements, design + testing plan, tasks) is "
        "ready for its human gate."
    ),
    "pr-review-pending": (
        "A pull request delivering the work item is ready for human review."
    ),
    "security-sign-off-pending": (
        "The work item's risk tier requires a named human security sign-off."
    ),
    "conflict-escalated": (
        "The loop hit a genuine block, logged the conflict and escalated once."
    ),
    "work-item-complete": "The work item reached `complete`.",
}
