"""How the-loop speaks in a room (issue-393 B4, the room rework).

The old room message opened with a machine header — the raw event type and the
full ``github:<host>/<owner>/<repo>#N`` ref, the same 50 characters on all 41
messages — and read like a log line whoever it was addressed to. This module is
the other voice: one state-carrying emoji and a first-person, present-tense
sentence, the way a colleague talks. It maps an event to ``(emoji, lead)`` and
composes the line the room sees; the header is dropped for a room (the room's
binding already says which item it is) and kept only for a shared channel, where
a short ``#<n> title`` link identifies the item instead of the raw ref (R7).

Pure and offline: a table and a formatter, no Slack, no disk. The channel calls
:func:`room_lead` for a room-bound message and keeps the classic header for a
shared channel or the ``classic`` style.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

__all__ = [
    "EMOJI",
    "emoji_for",
    "room_lead",
    "channel_header",
]

#: The one emoji each kind of moment carries (the report's palette). Keyed by
#: event type; a kind with no entry gets no emoji rather than a wrong one.
EMOJI: Dict[str, str] = {
    "work-item.started": "🚀",
    "phase-selection": "🚀",
    "session.awaiting_input": "🤔",
    "decision-pending": "🤔",
    "phase-approval-pending": "📋",
    "security-sign-off-pending": "📋",
    "gate.acknowledged": "✅",
    "phase.started": "🔨",
    "phase.progress": "🔨",
    "session.progress": "🔨",
    "phase.completed": "✅",
    "pr-review-pending": "👀",
    "work-item-complete": "🎉",
    "work-item.closed": "🎉",
    "conflict-escalated": "⚠️",
    "control.rejected": "⚠️",
}

#: The default when an event type has no emoji of its own — a neutral speech mark
#: rather than nothing, so every room line still reads as the-loop talking.
_DEFAULT_EMOJI = "💬"


def emoji_for(event_type: str) -> str:
    """The state emoji for ``event_type`` (the default speech mark when none)."""
    return EMOJI.get(event_type, _DEFAULT_EMOJI)


def room_lead(event: Any) -> str:
    """The first line for a room-bound message: one emoji, then the event's own
    text — no machine header (R7.1), no robot-face signature (R11.2).

    The text is the event's ``text`` (already the first-person sentence its
    emitter wrote, since the rework); when it is empty a short fallback names the
    moment so a room line is never a bare emoji. The emoji is prepended once, and
    never doubled if the text already starts with it.
    """
    emoji = emoji_for(str(getattr(event, "event_type", "") or ""))
    text = str(getattr(event, "text", "") or "").strip()
    if not text:
        text = _fallback_lead(event)
    if text.startswith(emoji):
        return text
    return f"{emoji} {text}"


def channel_header(event: Any, *, title_of: Optional[Dict[str, str]] = None) -> str:
    """The identifier line for a message in a SHARED channel (not a room): a
    short ``#<n> <title>`` for the work item rather than the 50-char ref (R7.2).

    ``title_of`` optionally maps a work-item ref to its title; without it, or
    without a match, the short id alone is used. Never the raw event type.
    """
    ref = str(getattr(event, "work_item", "") or "")
    short = _short_id(ref)
    title = (title_of or {}).get(ref, "") if title_of else ""
    emoji = emoji_for(str(getattr(event, "event_type", "") or ""))
    label = f"{short} {title}".strip() if title else short
    return f"{emoji} {label}".strip()


def _short_id(ref: str) -> str:
    """``github:octo/repo#15`` → ``#15``; a non-standard ref returns itself."""
    if "#" in ref:
        return "#" + ref.rsplit("#", 1)[1]
    return ref


def _fallback_lead(event: Any) -> str:
    """A short first-person line when an event carried no text of its own."""
    event_type = str(getattr(event, "event_type", "") or "")
    node = ""
    detail = getattr(event, "detail", None) or {}
    node = str(detail.get("node") or detail.get("phase") or "")
    known = {
        "phase.started": f"Starting {node}." if node else "Starting the next phase.",
        "phase.completed": f"Finished {node}." if node else "Phase done.",
        "work-item-complete": "All done — merged and closed.",
        "work-item.closed": "Closed.",
        "session.awaiting_input": "I have a question for you.",
        "phase-approval-pending": "This is ready for your approval.",
        "pr-review-pending": "The pull request is ready for review.",
    }
    return known.get(event_type, "Update on this work item.")
