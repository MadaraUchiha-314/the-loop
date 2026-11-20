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


def test_outside_a_room_the_room_only_rules_do_not_fire():
    """issue-549 design.md stage 1: the policy runs for every conversation, but
    session-wins keeps its room-only scope. (transition-collapse is gone: the
    `phase.*` pair it folded is bookkeeping since issue-549 R10.)"""
    spoken = decide(
        _event("comment.agent", detail={"node": "design"}),
        {"sessionSpokeFor": "design"},
        is_room=False,
    )
    assert spoken.action == POST


def test_outside_a_room_progress_edit_and_gate_memory_apply():
    """issue-549 design.md stage 1: progress-edit (R6) and gate memory (R11.6)
    act in the central channel too."""
    progress = decide(
        _event("phase.progress", detail={"phase": "design"}),
        {"progressTs": {"design": "1700.5"}},
        is_room=False,
    )
    assert progress.action == EDIT and progress.ts == "1700.5"
    gate = decide(
        _event("phase-approval-pending", detail={"node": "design-approval"}),
        {},
        is_room=False,
    )
    assert gate.action == POST and gate.remember == {
        "gateTs": {"design-approval": "@ts"}
    }


# -- dedupe (R6.4) --------------------------------------------------------------


def test_the_identical_event_for_the_same_node_is_dropped():
    memory = {"lastEvent": "work-item-complete", "lastNode": "complete"}
    d = decide(
        _event("work-item-complete", detail={"node": "complete"}),
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
    """The gate's `phase.started` line is a label change, so bookkeeping drops
    it before gate-collapse is asked (issue-549 R10.1)."""
    memory = {"gateTs": {"requirements-approval": "1700.1"}}
    d = decide(
        _event("phase.started", detail={"node": "requirements-approval"}),
        memory,
        is_room=True,
    )
    assert d.action == DROP and d.rule == "bookkeeping"


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


def test_the_nodeless_ready_for_review_mirror_reads_its_node_from_the_text():
    """The live mirror (issue N2) carries NO detail node — the collapse reads the
    node from the `request-review` body, "**<node>** is ready for review"."""
    memory = {"gateTs": {"requirements-approval": "1700.1"}}
    d = decide(
        _event(
            "comment.agent",
            text=(
                "🤖 _the-loop_ — **requirements-approval** is ready for review.\n\n"
                "Work item `issue-3` has reached a human gate. Reply with an approval…"
            ),
        ),
        memory,
        is_room=True,
    )
    assert d.action == DROP and d.rule == "gate-collapse"


def test_a_ready_for_review_mirror_for_an_already_answered_gate_posts():
    """A "ready for review" mirror naming a node with no live gateTs is not
    collapsed — the gate it names is not the one open now."""
    memory = {"gateTs": {"requirements-approval": "1700.1"}}
    d = decide(
        _event(
            "comment.agent",
            text="**design-approval** is ready for review.",
        ),
        memory,
        is_room=True,
    )
    assert d.action == POST


def test_the_phase_progress_at_a_gated_node_is_collapsed():
    """An approval node inherits its predecessor's phase, so entering it emits
    `phase.progress`, not `phase.started` (issue N2) — gate-collapse must drop it
    too, or the gate is announced twice."""
    memory = {"gateTs": {"requirements-approval": "1700.1"}}
    d = decide(
        _event("phase.progress", detail={"node": "requirements-approval"}),
        memory,
        is_room=True,
    )
    assert d.action == DROP and d.rule == "gate-collapse"


def test_a_phase_progress_at_an_ungated_node_still_edits_in_place():
    """The review-chain progress (issue-393 R6.3) must keep editing its message —
    only a GATED node's progress is collapsed."""
    memory = {"progressTs": {"needs-review": "1700.5"}}
    d = decide(
        _event(
            "phase.progress", detail={"node": "critic-review", "phase": "needs-review"}
        ),
        memory,
        is_room=True,
    )
    assert d.action == EDIT and d.rule == "progress-edit" and d.ts == "1700.5"


_CHEAT_SHEET = (
    "🖥️ **the-loop** started an interactive session for `issue-3`.\n\n"
    "| tmux session | `loop-issue-3` |\n\n"
    "```sh\ntmux attach -t loop-issue-3\n```\n"
)


def test_the_session_started_cheat_sheet_mirror_is_bookkeeping():
    """issue-549 R10.1 (replacing issue N2's word match): the tmux cheat-sheet
    mirror is recognised by the `session-started` notice kind the GitHub mirror
    read from its hidden marker."""
    d = decide(
        _event(
            "comment.agent", text=_CHEAT_SHEET, detail={"notice": "session-started"}
        ),
        {},
        is_room=True,
    )
    assert d.action == DROP and d.rule == "bookkeeping"


def test_bookkeeping_dropped_by_kind_not_by_words():
    """issue-549 design.md (Bookkeeping detection): words change with every
    string edit, so the cheat-sheet's words alone, with no notice kind, are an
    ordinary comment."""
    d = decide(_event("comment.agent", text=_CHEAT_SHEET), {}, is_room=True)
    assert d.action == POST


def test_an_ordinary_comment_mentioning_a_session_is_not_operator_docs():
    d = decide(
        _event("comment.agent", text="I restarted the session; it looks fine now."),
        {},
        is_room=True,
    )
    assert d.action == POST


def test_the_terminal_nodes_own_lifecycle_lines_are_collapsed():
    """The `complete` node's phase.started/completed say nothing the dedicated
    completion and closure events (and the session's summary) do not (issue N2);
    since issue-549 R10 every `phase.*` line is bookkeeping."""
    started = decide(
        _event("phase.started", detail={"node": "complete"}),
        {"lastEvent": "work-item-complete", "lastNode": "complete"},
        is_room=True,
    )
    completed = decide(
        _event("phase.completed", detail={"node": "complete"}),
        {"lastEvent": "phase.started", "lastNode": "x"},
        is_room=True,
    )
    assert started.action == DROP and started.rule == "bookkeeping"
    assert completed.action == DROP and completed.rule == "bookkeeping"


def test_the_completion_and_closure_events_themselves_still_post():
    """bookkeeping drops only the terminal node's phase pair — the events
    that actually announce the end still reach the room."""
    complete = decide(
        _event("work-item-complete", detail={"node": "complete"}), {}, is_room=True
    )
    closed = decide(_event("work-item.closed"), {}, is_room=True)
    assert complete.action == POST and closed.action == POST


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
    assert d.action == DROP and d.rule == "bookkeeping"


def test_a_terminal_completed_is_bookkeeping_too():
    """issue-549 R10.1: a terminal `phase.completed` is still a label change;
    `work-item-complete` is what announces the end."""
    d = decide(
        _event("phase.completed", detail={"node": "complete", "terminal": "true"}),
        {},
        is_room=True,
    )
    assert d.action == DROP and d.rule == "bookkeeping"


# -- session-wins (R12.3) -------------------------------------------------------


def test_a_template_for_a_moment_the_session_spoke_for_is_dropped():
    memory = {"sessionSpokeFor": "requirements-definition"}
    d = decide(
        _event("comment.agent", detail={"node": "requirements-definition"}),
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


# -- bookkeeping (issue-549 R10) --------------------------------------------------


def test_bookkeeping_dropped_phase_started_and_completed_everywhere():
    """issue-549 R10.1: a `loop:<phase>` label change is never posted to Slack,
    in a room or in the central channel."""
    for event_type in ("phase.started", "phase.completed"):
        for is_room in (True, False):
            d = decide(
                _event(event_type, detail={"node": "design", "phase": "design"}),
                {},
                is_room=is_room,
            )
            assert d.action == DROP and d.rule == "bookkeeping", (event_type, is_room)


def test_bookkeeping_dropped_session_started_notice_in_the_central_channel():
    """issue-549 R10.1: the session-started notice is dropped wherever it goes."""
    d = decide(
        _event("comment.agent", text="anything", detail={"notice": "session-started"}),
        {},
        is_room=False,
    )
    assert d.action == DROP and d.rule == "bookkeeping"


def test_bookkeeping_dropped_only_for_bookkeeping_kinds():
    """A notice kind that is not bookkeeping, and the progress line, still post."""
    other = decide(
        _event("comment.agent", text="hi", detail={"notice": "something-else"}),
        {},
        is_room=True,
    )
    progress = decide(
        _event("phase.progress", detail={"phase": "design"}), {}, is_room=True
    )
    assert other.action == POST and progress.action == POST
