"""The room's voice: emoji + first-person lead, no machine header (issue-393 B4).

Pure table and formatter tests, plus render_blocks in agentic mode.

Spec: docs/specs/issue-393/{requirements,design}.md (R7, R11).
"""

from __future__ import annotations

import json

from the_loop.channels.base import Event
from the_loop.channels.slack import render_blocks
from the_loop.channels.voice import channel_header, emoji_for, room_lead

REF = "github:octo/repo#1"


def _event(event_type, *, text="", detail=None):
    return Event(event_type=event_type, work_item=REF, text=text, detail=detail or {})


def test_each_moment_carries_its_state_emoji():
    assert emoji_for("work-item.started") == "🚀"
    assert emoji_for("session.awaiting_input") == "🤔"
    assert emoji_for("phase-approval-pending") == "📋"
    assert emoji_for("pr-review-pending") == "👀"
    assert emoji_for("work-item-complete") == "🎉"
    assert emoji_for("control.rejected") == "⚠️"


def test_an_unmapped_event_gets_the_neutral_speech_mark_never_a_wrong_one():
    assert emoji_for("some.new.event") == "💬"


def test_the_room_lead_is_the_emoji_and_the_events_own_sentence():
    lead = room_lead(_event("pr-review-pending", text="PR #2 is ready: +840/−19."))
    assert lead == "👀 PR #2 is ready: +840/−19."


def test_the_room_lead_never_doubles_an_emoji_the_text_already_has():
    lead = room_lead(_event("work-item-complete", text="🎉 Merged and closed."))
    assert lead == "🎉 Merged and closed."
    assert lead.count("🎉") == 1


def test_the_room_lead_falls_back_to_a_sentence_when_the_event_has_no_text():
    lead = room_lead(_event("phase.started", detail={"node": "design"}))
    assert lead == "🔨 Starting design."


def test_a_shared_channel_header_is_a_short_id_and_title_not_the_raw_ref():
    header = channel_header(
        _event("phase-approval-pending"),
        title_of={REF: "Add a repository health check"},
    )
    assert header == "📋 #1 Add a repository health check"
    assert "github:octo/repo" not in header


# -- render_blocks in agentic mode ----------------------------------------------


def test_agentic_render_drops_the_machine_header():
    event = _event(
        "phase.started",
        text="🔨 On to the design.",
        detail={"node": "design"},
    )
    blocks = render_blocks(event, "normal", agentic=True)
    rendered = json.dumps(blocks)
    # no header block, no raw event type, no full ref
    assert not any(b.get("type") == "header" for b in blocks)
    assert "phase.started" not in rendered
    assert "github:octo/repo#1" not in rendered
    assert "On to the design." in rendered


def test_classic_render_keeps_the_header():
    event = _event(
        "phase-approval-pending",
        text="ready",
        detail={"node": "requirements-approval"},
    )
    blocks = render_blocks(event, "normal", agentic=False)
    assert any(b.get("type") == "header" for b in blocks)
