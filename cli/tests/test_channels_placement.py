"""Placement (issue-549 task 8): one rule for where each form of an event goes.

The table in design.md § User-visible behaviour, one case per row:

| Where                    | short message                         | long form                  |
|--------------------------|---------------------------------------|----------------------------|
| declared room            | top-level in the room                 | in the short message's thread |
| central channel          | reply in the work item's thread       | none (R4.2)                |
| mention thread in a room | reply in that thread                  | after it, same thread      |
| mention in central       | as central (R4.3)                     | none                       |

Buttons are always on the short message (R4.4); *Open on GitHub* when the event
has a URL (R3.2, R4.2). Pure.

Spec: docs/specs/issue-549/{requirements,design}.md (R4.1–R4.4).
"""

from __future__ import annotations

import pytest

from the_loop.channels.base import Event
from the_loop.channels.placement import (
    CENTRAL,
    CONVERSATION_KINDS,
    ITEM_THREAD,
    MENTION_THREAD,
    ROOM,
    ROOM_MENTION_THREAD,
    SHORT_THREAD,
    TOP_LEVEL,
    Placement,
    place,
)

URL = "https://github.com/octo/repo/issues/1#issuecomment-2"


def _event(text="The whole long form.", url=URL):
    return Event(
        event_type="comment.agent", work_item="github:octo/repo#1", text=text, url=url
    )


@pytest.mark.parametrize(
    "kind, short, long",
    [
        (ROOM, TOP_LEVEL, SHORT_THREAD),  # R4.1
        (CENTRAL, ITEM_THREAD, ""),  # R4.2: no long form in central
        (ROOM_MENTION_THREAD, MENTION_THREAD, MENTION_THREAD),  # R4.3
    ],
)
def test_placement_table(kind, short, long):
    placed = place(kind, _event())
    assert placed == Placement(short=short, long=long, open_on_github=True)
    assert placed.buttons_on_short  # R4.4


def test_mention_in_central_follows_central():
    # R4.3: the answer to a mention in the central channel is placed as R4.2
    assert place(CENTRAL, _event()).long == ""


@pytest.mark.parametrize("kind", CONVERSATION_KINDS)
def test_no_url_no_open_on_github_button(kind):
    assert place(kind, _event(url="")).open_on_github is False


@pytest.mark.parametrize("kind", CONVERSATION_KINDS)
def test_no_long_form_when_it_adds_nothing(kind):
    # R3.3: a long form that adds nothing to the short form posts no reply
    assert place(kind, _event(), long_adds=False).long == ""
    assert place(kind, _event(text="  \n")).long == ""


def test_unknown_kind_is_refused():
    with pytest.raises(ValueError):
        place("somewhere", _event())


def test_kinds_are_the_three_conversations():
    assert set(CONVERSATION_KINDS) == {ROOM, CENTRAL, ROOM_MENTION_THREAD}
