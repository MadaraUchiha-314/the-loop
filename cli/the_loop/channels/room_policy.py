"""What a room is told, and how (issue-393 B3, the room rework).

The runtime, the graph hooks and the GitHub→room mirror each compose a finished
event and hand it to the Slack channel, which used to post every one of them —
top-level, with a machine header. For one small work item that was 41 messages
in two hours: 22 of them ``phase.started``/``phase.completed`` pairs seconds
apart, every gate announced three times, a tmux cheat-sheet, a checklist of
glyphs. A person on a phone muted the channel before the requirements were drafted.

This module is the seam that makes the room read like a conversation instead of a
log. It is a **pure decision** over an event and the room's delivery memory
(:class:`the_loop.channels.state.ChannelState`'s per-work-item record): given one
event, does the room get a new message, an edit of a message already there, a
threaded reply, or nothing — and *why*. It talks to no Slack and no disk, so
every rule is a unit test; the channel applies the decision and records what it
did back into the memory the next decision reads.

The GitHub ledger never passes through here — collapse and suppression are a
**delivery** policy for the room, not a change to what happened. An operator can
still reconstruct the whole run from the ticket, exactly as before.

The rules, in the order they are consulted (:func:`decide`):

* **dedupe** — the identical event for the same node was already delivered → drop.
* **gate-collapse** — a ``phase.started`` line or a mirrored "ready for review"
  comment for a node whose ``*-pending`` approval message was just posted → drop;
  the message with the buttons is the one announcement a gate gets.
* **transition-collapse** — a ``phase.completed`` immediately followed by the
  successor's ``phase.started`` is one transition; the completed half is dropped
  and the started half carries it.
* **progress-edit** — a within-phase progress event edits that phase's one
  message in place rather than posting a new one.
* **ack-thread** — an acknowledgement of a consumed gate answer threads under the
  gate's own message.
* **session-wins** — a runtime template for a moment the session already spoke
  for is dropped.
* **operator-docs** — a tmux cheat-sheet / shell block is for the ticket, never
  the room.

Anything no rule claims is posted, top-level, in the room's own voice
(:mod:`the_loop.channels.voice`). The whole module is a no-op when the target is
not a room (a shared channel or an unbound post): the rework is for the place a
single work item lives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping

__all__ = [
    "Decision",
    "POST",
    "DROP",
    "EDIT",
    "THREAD",
    "decide",
    "GATE_PENDING_EVENTS",
    "LIFECYCLE_EVENTS",
    "PROGRESS_EVENTS",
]

#: The four things that can happen to a room-bound event.
POST = "post"  # a new top-level message
DROP = "drop"  # nothing (the `rule` says which rule claimed it)
EDIT = "edit"  # chat.update the message at `ts`
THREAD = "thread"  # a reply under the message at `ts`

#: Events that carry a gate's approval request — the one announcement a gate gets.
GATE_PENDING_EVENTS = frozenset({"phase-approval-pending", "pr-review-pending"})

#: The lifecycle pair the transition-collapse rule folds into one line.
LIFECYCLE_EVENTS = frozenset({"phase.started", "phase.completed"})

#: Within-phase progress events that edit the phase's one message in place. An
#: event type ending in ``.progress`` is treated as progress too, so a new
#: progress event kind is covered without editing this set.
PROGRESS_EVENTS = frozenset({"phase.progress", "session.progress"})

#: A mirrored agent comment reaches the room as this event type (the GitHub→room
#: mirror). Suppressed by gate-collapse when it is a gate's "ready for review".
MIRROR_EVENT = "comment.agent"


@dataclass(frozen=True)
class Decision:
    """What to do with one room-bound event, and why.

    ``action`` is one of :data:`POST`/:data:`DROP`/:data:`EDIT`/:data:`THREAD`.
    ``rule`` names the rule that decided it — logged by the channel so a
    "missing" message is diagnosable from the daemon log alone (the NFR). ``ts``
    is the message to edit or thread under, for :data:`EDIT`/:data:`THREAD`.
    ``remember`` is what the channel should merge into the delivery memory after
    it acts (e.g. the new message's ts under this phase), so the memory the next
    decision reads is current.
    """

    action: str
    rule: str = ""
    ts: str = ""
    remember: Mapping[str, Any] = field(default_factory=dict)


def _node_of(event: Any) -> str:
    """The graph node an event is about, from its detail — ``""`` when it names
    none (a non-lifecycle event the rules do not key on a node)."""
    detail = getattr(event, "detail", None) or {}
    return str(detail.get("node") or detail.get("phase") or "")


def _phase_of(event: Any) -> str:
    detail = getattr(event, "detail", None) or {}
    return str(detail.get("phase") or detail.get("node") or "")


def _is_progress(event_type: str) -> bool:
    return event_type in PROGRESS_EVENTS or event_type.endswith(".progress")


def decide(
    event: Any,
    memory: Mapping[str, Any],
    *,
    is_room: bool,
    session_authored: bool = False,
    is_operator_doc: bool = False,
) -> Decision:
    """The room's decision for ``event`` given its delivery ``memory``.

    ``memory`` is a work item's :meth:`ChannelState.delivery_for` record.
    ``is_room`` is False for a shared channel or an unbound post, where the whole
    rework is off and every event simply posts. ``session_authored`` marks an
    event the session itself wrote (its question or summary), which wins over a
    runtime template for the same moment. ``is_operator_doc`` marks operator
    documentation (a tmux cheat-sheet) that never belongs in a room.

    Pure: it reads ``event`` and ``memory``, returns a :class:`Decision`, and
    changes nothing.
    """
    event_type = str(getattr(event, "event_type", "") or "")

    # Outside a room the rework does not apply: a shared channel and an unbound
    # post get every event, top-level, exactly as before.
    if not is_room:
        return Decision(POST, rule="not-a-room")

    # operator-docs — for the ticket, never a room.
    if is_operator_doc:
        return Decision(DROP, rule="operator-docs")

    node = _node_of(event)
    last_event = str(memory.get("lastEvent") or "")
    last_node = str(memory.get("lastNode") or "")
    gate_ts: Dict[str, str] = dict(memory.get("gateTs") or {})
    progress_ts: Dict[str, str] = dict(memory.get("progressTs") or {})

    # dedupe — the very same event for the very same node, already delivered.
    # (Two exact `phase.completed *complete*` were posted in the e2e run.)
    if event_type and event_type == last_event and node and node == last_node:
        return Decision(DROP, rule="dedupe")

    # session-wins — the session already spoke for this moment; drop the template.
    # A session-authored event itself always posts (it IS the winning message).
    if not session_authored and _template_superseded(event, memory):
        return Decision(DROP, rule="session-wins")

    # gate-collapse — a gate announces once, with its buttons. After a `*-pending`
    # for a node, that node's `phase.started` line and its mirrored "ready for
    # review" comment are noise.
    if node and gate_ts.get(node):
        if event_type == "phase.started":
            return Decision(DROP, rule="gate-collapse")
        if event_type == MIRROR_EVENT and _looks_like_ready_for_review(event):
            return Decision(DROP, rule="gate-collapse")

    # A gate's own pending message: post it, and remember its ts so the collapse
    # above and the ack-thread below can find it.
    if event_type in GATE_PENDING_EVENTS and node:
        return Decision(POST, rule="gate-pending", remember={"gateTs": {node: "@ts"}})

    # ack-thread — an acknowledgement of a consumed gate answer threads under the
    # gate's message rather than starting a new top-level line.
    if _is_ack(event) and node and gate_ts.get(node):
        return Decision(THREAD, rule="ack-thread", ts=gate_ts[node])

    # progress-edit — a within-phase progress event edits that phase's one
    # message; the first one posts and is remembered, the rest edit it.
    if _is_progress(event_type):
        phase = _phase_of(event)
        existing = progress_ts.get(phase)
        if existing:
            return Decision(EDIT, rule="progress-edit", ts=existing)
        return Decision(
            POST, rule="progress-open", remember={"progressTs": {phase: "@ts"}}
        )

    # transition-collapse — `phase.completed` immediately followed by the
    # successor's `phase.started` is one transition. Drop the completed half; the
    # started half (next call) carries the move. Only when the completed event is
    # not itself a terminal "done" the room should hear.
    if event_type == "phase.completed" and not _is_terminal(event):
        return Decision(DROP, rule="transition-collapse")

    # Anything else: a new top-level message, remembered as the last thing said.
    return Decision(
        POST,
        rule="post",
        remember={"lastEvent": event_type, "lastNode": node},
    )


def _template_superseded(event: Any, memory: Mapping[str, Any]) -> bool:
    """Whether a runtime template restates a moment the session already spoke for.

    The session marks its own announcement in the memory (``sessionSpokeFor`` →
    the node); a later runtime template for that same node is the duplicate the
    room does not need (R12.3). Conservative: only a lifecycle/mirror template
    keyed on that exact node is dropped, never a distinct event.
    """
    spoke_for = str(memory.get("sessionSpokeFor") or "")
    if not spoke_for:
        return False
    event_type = str(getattr(event, "event_type", "") or "")
    if event_type not in LIFECYCLE_EVENTS and event_type != MIRROR_EVENT:
        return False
    return _node_of(event) == spoke_for


def _looks_like_ready_for_review(event: Any) -> bool:
    """Whether a mirrored comment is a gate's "ready for review" restatement —
    the one the `*-pending` message already made actionable."""
    text = str(getattr(event, "text", "") or "").lower()
    return "ready for review" in text or "reply with an approval" in text


def _is_ack(event: Any) -> bool:
    """Whether an event is an acknowledgement of a consumed gate answer."""
    detail = getattr(event, "detail", None) or {}
    return (
        bool(detail.get("ack"))
        or str(getattr(event, "event_type", "")) == "gate.acknowledged"
    )


def _is_terminal(event: Any) -> bool:
    """Whether a `phase.completed` is the run's own end (the room should hear a
    completion), not an intermediate one to collapse into the next start."""
    detail = getattr(event, "detail", None) or {}
    return bool(detail.get("terminal")) or _node_of(event) in ("complete", "done")
