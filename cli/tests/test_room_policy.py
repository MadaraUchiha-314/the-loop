"""RoomPolicy: what a room is told, and how (issue-393 B3).

A pure decision over an event and the room's delivery memory — no Slack, no
disk. One test per rule in `decide`, plus the not-a-room short-circuit and the
memory the channel is told to remember.

Spec: docs/specs/issue-393/{requirements,design}.md (R6, R10, R11.3, R12.3).
"""

from __future__ import annotations

from the_loop.channels.base import Event
from the_loop.channels.room_policy import (
    DROP,
    EDIT,
    POST,
    THREAD,
    decide,
)

REF = "github:octo/repo#1"


def _event(event_type, *, text="", detail=None, summary=""):
    return Event(
        event_type=event_type,
        work_item=REF,
        text=text,
        detail=detail or {},
        summary=summary,
    )


# -- the room/not-a-room boundary -----------------------------------------------


def test_outside_a_room_every_event_simply_posts():
    d = decide(_event("phase.started"), {}, is_room=False)
    assert d.action == POST and d.rule == "not-a-room"


# -- dedupe (R6.4) --------------------------------------------------------------


def test_the_identical_event_for_the_same_node_is_dropped():
    memory = {"lastEvent": "phase.completed", "lastNode": "complete"}
    d = decide(
        _event("phase.completed", detail={"node": "complete"}),
        memory,
        is_room=True,
    )
    assert d.action == DROP and d.rule == "dedupe"


# -- gate-collapse (R6.2) -------------------------------------------------------


def test_a_gate_pending_posts_and_remembers_its_ts():
    d = decide(
        _event("phase-approval-pending", detail={"node": "requirements-approval"}),
        {},
        is_room=True,
    )
    assert d.action == POST and d.rule == "gate-pending"
    assert d.remember["gateTs"] == {"requirements-approval": "@ts"}


def test_the_phase_started_line_after_a_gate_pending_is_dropped():
    memory = {"gateTs": {"requirements-approval": "1700.1"}}
    d = decide(
        _event("phase.started", detail={"node": "requirements-approval"}),
        memory,
        is_room=True,
    )
    assert d.action == DROP and d.rule == "gate-collapse"


def test_the_ready_for_review_mirror_after_a_gate_pending_is_dropped():
    memory = {"gateTs": {"design-approval": "1700.1"}}
    d = decide(
        _event(
            "comment.agent",
            text="*design-approval* is ready for review — reply with an approval",
            detail={"node": "design-approval"},
        ),
        memory,
        is_room=True,
    )
    assert d.action == DROP and d.rule == "gate-collapse"


# -- ack-thread (R10.1) ---------------------------------------------------------


def test_a_gate_acknowledgement_threads_under_the_gate_message():
    memory = {"gateTs": {"requirements-approval": "1700.5"}}
    d = decide(
        _event("gate.acknowledged", detail={"node": "requirements-approval"}),
        memory,
        is_room=True,
    )
    assert d.action == THREAD and d.rule == "ack-thread" and d.ts == "1700.5"


# -- progress-edit (R6.3 / R10.2) -----------------------------------------------


def test_the_first_progress_message_posts_and_is_remembered():
    d = decide(
        _event("phase.progress", detail={"phase": "verification"}),
        {},
        is_room=True,
    )
    assert d.action == POST and d.rule == "progress-open"
    assert d.remember["progressTs"] == {"verification": "@ts"}


def test_a_later_progress_message_edits_the_phase_message_in_place():
    memory = {"progressTs": {"verification": "1700.9"}}
    d = decide(
        _event("phase.progress", detail={"phase": "verification"}),
        memory,
        is_room=True,
    )
    assert d.action == EDIT and d.rule == "progress-edit" and d.ts == "1700.9"


# -- transition-collapse (R6.1) -------------------------------------------------


def test_an_intermediate_completed_is_collapsed():
    d = decide(
        _event("phase.completed", detail={"node": "design"}),
        {},
        is_room=True,
    )
    assert d.action == DROP and d.rule == "transition-collapse"


def test_a_terminal_completed_is_still_heard():
    d = decide(
        _event("phase.completed", detail={"node": "complete", "terminal": "true"}),
        {},
        is_room=True,
    )
    assert d.action == POST


# -- session-wins (R12.3) -------------------------------------------------------


def test_a_template_for_a_moment_the_session_spoke_for_is_dropped():
    memory = {"sessionSpokeFor": "requirements-definition"}
    d = decide(
        _event("phase.started", detail={"node": "requirements-definition"}),
        memory,
        is_room=True,
    )
    assert d.action == DROP and d.rule == "session-wins"


def test_a_session_authored_event_always_posts():
    memory = {"sessionSpokeFor": "requirements-definition"}
    d = decide(
        _event("session.awaiting_input", detail={"node": "requirements-definition"}),
        memory,
        is_room=True,
        session_authored=True,
    )
    assert d.action == POST


# -- operator-docs (R11.3) ------------------------------------------------------


def test_operator_documentation_never_reaches_a_room():
    d = decide(
        _event("session.started", text="tmux cheat-sheet"),
        {},
        is_room=True,
        is_operator_doc=True,
    )
    assert d.action == DROP and d.rule == "operator-docs"


# -- the default ----------------------------------------------------------------


def test_an_ordinary_event_posts_and_records_itself():
    d = decide(
        _event("work-item.closed", detail={"node": "complete"}),
        {},
        is_room=True,
    )
    assert d.action == POST and d.rule == "post"
    assert d.remember == {"lastEvent": "work-item.closed", "lastNode": "complete"}
