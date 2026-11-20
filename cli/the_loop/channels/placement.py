"""Where each form of an event goes in Slack (issue-549, task 8).

One rule, read by both builders and the delivery step, so no other component
needs to know whether it is in a room (design.md § Architecture, stage 2):

* **declared room** (issue-375): the short form is a top-level message in the
  room; the long form goes in that message's thread (R4.1).
* **central channel**: the short form is a reply in the work item's thread;
  no long form, because a thread reply cannot have a thread of its own and
  Slack has no fold the-loop controls (R4.2). An answer to a mention in the
  central channel is placed the same way (R4.3).
* **mention thread in a room** (issue-507): the short form is the reply in that
  thread, and the long form follows it in the same thread (R4.3).

Gate buttons, command buttons and the phase-selection control are always part
of the short message, so a decision is taken from the top-level message (R4.4).
The *Open on GitHub* button is there whenever the event has a URL (R3.2). Pure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple

__all__ = [
    "CENTRAL",
    "CONVERSATION_KINDS",
    "ITEM_THREAD",
    "MENTION_THREAD",
    "ROOM",
    "ROOM_MENTION_THREAD",
    "SHORT_THREAD",
    "TOP_LEVEL",
    "Placement",
    "place",
]

#: The conversation an event is delivered to.
ROOM = "room"  # a declared room (issue-375)
CENTRAL = "central"  # the central channel, one thread per work item
ROOM_MENTION_THREAD = "room-mention-thread"  # a mention thread in a room (issue-507)
CONVERSATION_KINDS: Tuple[str, ...] = (ROOM, CENTRAL, ROOM_MENTION_THREAD)

#: Where a message goes.
TOP_LEVEL = "top-level"  # a new top-level message in the room
ITEM_THREAD = "item-thread"  # a reply in the work item's thread (central)
MENTION_THREAD = "mention-thread"  # a reply in the thread of the mention
SHORT_THREAD = "short-thread"  # a reply in the thread of the short message


@dataclass(frozen=True)
class Placement:
    """Where one event's forms go.

    ``short`` is where the short message goes (:data:`TOP_LEVEL`,
    :data:`ITEM_THREAD` or :data:`MENTION_THREAD`). ``long`` is where the
    long-form parts go, after it and in order (:data:`SHORT_THREAD` or
    :data:`MENTION_THREAD`), or ``""`` for none. ``open_on_github`` says the
    short message carries the *Open on GitHub* button.
    """

    short: str
    long: str
    open_on_github: bool

    @property
    def buttons_on_short(self) -> bool:
        """Gate and command buttons go on the short message, always (R4.4)."""
        return True


_RULES = {
    ROOM: (TOP_LEVEL, SHORT_THREAD),
    CENTRAL: (ITEM_THREAD, ""),
    ROOM_MENTION_THREAD: (MENTION_THREAD, MENTION_THREAD),
}


def place(kind: str, event: Any, *, long_adds: bool = True) -> Placement:
    """Where ``event``'s short form and long form go in a conversation of
    ``kind`` (one of :data:`CONVERSATION_KINDS`).

    ``long_adds`` is False when the long form says nothing the short form does
    not (:func:`the_loop.channels.shortform.long_form_adds`, R3.3); the long
    form is then not posted, as when the event has no text.
    """
    if kind not in _RULES:
        raise ValueError(f"not a conversation kind: {kind!r}")
    short, long = _RULES[kind]
    text = str(getattr(event, "text", "") or "")
    if not long_adds or not text.strip():
        long = ""
    url = str(getattr(event, "url", "") or "")
    return Placement(short=short, long=long, open_on_github=bool(url))
