"""Graph state — a cache, never an authority (issue-109, R8)."""

from __future__ import annotations

import json

from the_loop.graph.state import GraphState


def test_round_trip(tmp_path):
    state = GraphState(work_item="issue-1", current_node="design")
    state.enter("design")
    state.save(tmp_path)
    again = GraphState.load(tmp_path, "issue-1")
    assert again.current_node == "design"
    assert again.nodes["design"].attempts == 1


def test_missing_state_yields_a_fresh_one(tmp_path):
    assert GraphState.load(tmp_path, "issue-1").current_node == ""


def test_an_unparseable_state_is_kept_not_deleted(tmp_path):
    """R8.3 — a corrupt file may be the only record of what happened."""
    path = GraphState.path_for(tmp_path)
    path.write_text("{ not json")
    state = GraphState.load(tmp_path, "issue-1")
    assert state.current_node == ""
    assert path.is_file(), "the corrupt file must survive for post-mortem"


def test_a_non_object_state_is_ignored(tmp_path):
    GraphState.path_for(tmp_path).write_text("[1, 2, 3]")
    assert GraphState.load(tmp_path, "issue-1").current_node == ""


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path):
    GraphState(work_item="issue-1").save(tmp_path)
    leftovers = [
        p.name for p in tmp_path.iterdir() if p.name.startswith(".graph-state-")
    ]
    assert leftovers == []


def test_repeated_block_is_detected(tmp_path):
    """The signal to escalate rather than retry a third time (R8.5)."""
    state = GraphState(work_item="issue-1")
    assert state.note_block("design", "same finding") is False
    assert state.note_block("design", "same finding") is True
    assert state.note_block("design", "different") is False


def test_state_serialises_the_forced_ledger(tmp_path):
    state = GraphState(work_item="issue-1")
    state.forced.append({"from": "a", "to": "b", "reason": "why"})
    state.save(tmp_path)
    data = json.loads(GraphState.path_for(tmp_path).read_text())
    assert data["forced"][0]["reason"] == "why"


def test_state_serialises_selected_opt_in_phases(tmp_path):
    """issue-188 — a selection is a recorded fact with provenance, like a skip."""
    state = GraphState(work_item="issue-1")
    state.opt_ins["design-critic-review"] = {"via": "selection", "by": "@owner"}
    state.save(tmp_path)
    data = json.loads(GraphState.path_for(tmp_path).read_text())
    assert data["optIns"]["design-critic-review"]["by"] == "@owner"
    assert GraphState.load(tmp_path, "issue-1").opt_ins == state.opt_ins


def test_a_state_file_without_opt_ins_selects_nothing(tmp_path):
    """issue-188, backward compatibility — every pre-issue-188 state file. A
    work item already in flight was never offered the choice, so it made none,
    and the opt-in node it never saw is skipped rather than blocking it."""
    GraphState.path_for(tmp_path).write_text(
        json.dumps({"workItem": "issue-1", "currentNode": "design"}), encoding="utf-8"
    )
    state = GraphState.load(tmp_path, "issue-1")
    assert state.opt_ins == {}
    assert state.current_node == "design"
