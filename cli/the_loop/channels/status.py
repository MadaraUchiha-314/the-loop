"""The work item's state at a glance: one status reaction (issue-549 R8, task 12).

Every work item with a Slack conversation carries exactly one the-loop status
reaction, on its **status message**: the work item's thread root in the central
channel, the latest short message the-loop posted in a declared room (R8.2).

This module is the pure half: which state an event puts the work item in
(:func:`state_for`) and which reaction calls move the status from what the
delivery memory says is there to where it should be (:func:`plan_status`). The
Slack channel makes the calls after delivery, best effort, and records the new
status back into the memory, so it only ever removes a reaction it added itself
(R8.5). Nothing here talks to Slack or disk.

The five states and their Slack emoji names are fixed (design.md § Interfaces,
R9.4's rule for fixed behaviour) and documented in the channels capability doc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from .events import APPROVAL_EVENTS

__all__ = [
    "BLOCKED",
    "COMPLETE",
    "IN_REVIEW",
    "STATUS_EMOJI",
    "WAITING",
    "WORKING",
    "StatusPlan",
    "plan_status",
    "state_for",
]

WORKING = "working"
WAITING = "waiting"  # on a human
IN_REVIEW = "in-review"
BLOCKED = "blocked"  # or failed
COMPLETE = "complete"

#: The one Slack emoji name per state (R8.1): ⚙️ ⏳ 👀 🛑 ✅.
STATUS_EMOJI: Dict[str, str] = {
    WORKING: "gear",
    WAITING: "hourglass_flowing_sand",
    IN_REVIEW: "eyes",
    BLOCKED: "octagonal_sign",
    COMPLETE: "white_check_mark",
}

#: Events that wait on a person: the session's question, a decision, and every
#: gate that asks for an approval.
_WAITING_EVENTS = frozenset(
    {"session.awaiting_input", "decision-pending", *APPROVAL_EVENTS}
)
_COMPLETE_EVENTS = frozenset({"work-item-complete", "work-item.closed"})
# A stalled session is blocked until a person wakes it.
_BLOCKED_EVENTS = frozenset({"conflict-escalated", "session.stalled"})
#: The session moves again: its stall ended, or an ask's deadline
#: passed and it went ahead with its default.
_WORKING_EVENTS = frozenset({"session.stall_ended", "session.ask_default_taken"})
_LIFECYCLE = frozenset({"phase.started", "phase.progress", "phase.completed"})
_TERMINAL_NODES = frozenset({"complete", "done"})
_BLOCKED_NODES = frozenset({"escalated"})
_FAILED_OUTCOMES = frozenset({"fail", "failed", "failure", "error", "blocked"})


def _detail(event: Any) -> Mapping[str, Any]:
    return getattr(event, "detail", None) or {}


def state_for(event: Any) -> str:
    """The state ``event`` puts its work item in, or ``""`` when it says nothing
    about the state (a comment, a reply): the status then stays as it is.

    * complete — ``work-item-complete``, ``work-item.closed``, or a phase event
      at the terminal ``complete``/``done`` node;
    * blocked — ``conflict-escalated``, a stalled session, the ``escalated``
      node, an event type ending in ``failed``, or a failed outcome or status;
    * waiting — the session's question, a decision, an approval gate, a gate's
      lifecycle line (its node's actor is a human);
    * in review — a phase event at a node or phase named for review
      (self-review, critic-review, security-review, needs-review, …);
    * working — any other phase start or step, an acknowledged gate answer,
      the session-started notice, a stall that ended, an ask's default taken.

    A ``phase.completed`` short of the end says nothing: the next
    ``phase.started`` follows it and sets the state.
    """
    event_type = str(getattr(event, "event_type", "") or "")
    detail = _detail(event)
    node = str(detail.get("node") or "")
    phase = str(detail.get("phase") or "")
    outcome = str(detail.get("outcome") or detail.get("status") or "").lower()

    if event_type in _COMPLETE_EVENTS:
        return COMPLETE
    if (
        event_type in _BLOCKED_EVENTS
        or event_type.endswith((".failed", "-failed", "_failed"))
        or outcome in _FAILED_OUTCOMES
    ):
        return BLOCKED
    if event_type in _WAITING_EVENTS:
        return WAITING
    if event_type in _WORKING_EVENTS:
        return WORKING
    if event_type in _LIFECYCLE:
        if node in _TERMINAL_NODES or (
            event_type == "phase.completed" and bool(detail.get("terminal"))
        ):
            return COMPLETE
        if event_type == "phase.completed":
            return ""
        if node in _BLOCKED_NODES:
            return BLOCKED
        if str(detail.get("actor") or "") == "human":
            return WAITING
        if "review" in node or "review" in phase:
            return IN_REVIEW
        return WORKING
    if event_type == "gate.acknowledged" or bool(detail.get("ack")):
        return WORKING
    if str(detail.get("notice") or "") == "session-started":
        return WORKING
    return ""


@dataclass(frozen=True)
class StatusPlan:
    """The reaction calls that move the status, and the status to record.

    ``add`` and ``remove`` are ``(channel, ts, emoji name)`` or ``None``;
    ``status`` is the delivery memory's new ``{channel, ts, emoji}``.
    """

    add: Optional[Tuple[str, str, str]]
    remove: Optional[Tuple[str, str, str]]
    status: Mapping[str, str]


def plan_status(
    current: Mapping[str, Any], state: str, target: Tuple[str, str]
) -> Optional[StatusPlan]:
    """How to get from the ``current`` status (``{channel, ts, emoji}`` from the
    delivery memory: the reaction the-loop itself added) to ``state`` on the
    status message ``target`` (``(channel, ts)``; ``("", "")`` keeps the current
    message). ``None`` when nothing changes.

    The state ``""`` keeps the current emoji, moving it to a new status message
    when the message moved (R8.3); with no emoji yet it is working (R8.1). Only
    the reaction named in ``current`` is ever removed (R8.5).
    """
    old_channel = str(current.get("channel") or "")
    old_ts = str(current.get("ts") or "")
    old_emoji = str(current.get("emoji") or "")
    channel, ts = target
    if not ts:
        channel, ts = old_channel, old_ts
    if not ts or not channel:
        return None
    emoji = STATUS_EMOJI.get(state) or old_emoji or STATUS_EMOJI[WORKING]
    if (channel, ts, emoji) == (old_channel, old_ts, old_emoji):
        return None
    remove = (
        (old_channel, old_ts, old_emoji)
        if old_ts and old_channel and old_emoji
        else None
    )
    return StatusPlan(
        add=(channel, ts, emoji),
        remove=remove,
        status={"channel": channel, "ts": ts, "emoji": emoji},
    )
