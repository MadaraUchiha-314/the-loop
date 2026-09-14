"""Work-item state — a cache, never an authority (issue-109, R8).

``graph-state.json`` until issue-365 renamed it: the pointer and the node records
are the graph's, but the surface, the session, the model, the effort and the
repositories are facts about the **work item**, true whichever loop it walks.
"""

from __future__ import annotations

import json

from the_loop.graph.state import (
    LEGACY_STATE_FILENAME,
    STATE_FILENAME,
    WorkItemState,
)


def test_round_trip(tmp_path):
    state = WorkItemState(work_item="issue-1", current_node="design")
    state.enter("design")
    state.save(tmp_path)
    again = WorkItemState.load(tmp_path, "issue-1")
    assert again.current_node == "design"
    assert again.nodes["design"].attempts == 1


def test_missing_state_yields_a_fresh_one(tmp_path):
    assert WorkItemState.load(tmp_path, "issue-1").current_node == ""


def test_an_unparseable_state_is_kept_not_deleted(tmp_path):
    """R8.3 — a corrupt file may be the only record of what happened."""
    path = WorkItemState.path_for(tmp_path)
    path.write_text("{ not json")
    state = WorkItemState.load(tmp_path, "issue-1")
    assert state.current_node == ""
    assert path.is_file(), "the corrupt file must survive for post-mortem"


def test_a_non_object_state_is_ignored(tmp_path):
    WorkItemState.path_for(tmp_path).write_text("[1, 2, 3]")
    assert WorkItemState.load(tmp_path, "issue-1").current_node == ""


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path):
    WorkItemState(work_item="issue-1").save(tmp_path)
    leftovers = [
        p.name for p in tmp_path.iterdir() if p.name.startswith(".graph-state-")
    ]
    assert leftovers == []


def test_repeated_block_is_detected(tmp_path):
    """The signal to escalate rather than retry a third time (R8.5)."""
    state = WorkItemState(work_item="issue-1")
    assert state.note_block("design", "same finding") is False
    assert state.note_block("design", "same finding") is True
    assert state.note_block("design", "different") is False


def test_state_serialises_the_forced_ledger(tmp_path):
    state = WorkItemState(work_item="issue-1")
    state.forced.append({"from": "a", "to": "b", "reason": "why"})
    state.save(tmp_path)
    data = json.loads(WorkItemState.path_for(tmp_path).read_text())
    assert data["forced"][0]["reason"] == "why"


def test_state_serialises_selected_opt_in_phases(tmp_path):
    """issue-188 — a selection is a recorded fact with provenance, like a skip."""
    state = WorkItemState(work_item="issue-1")
    state.opt_ins["design-critic-review"] = {"via": "selection", "by": "@owner"}
    state.save(tmp_path)
    data = json.loads(WorkItemState.path_for(tmp_path).read_text())
    assert data["optIns"]["design-critic-review"]["by"] == "@owner"
    assert WorkItemState.load(tmp_path, "issue-1").opt_ins == state.opt_ins


def test_a_state_file_without_opt_ins_selects_nothing(tmp_path):
    """issue-188, backward compatibility — every pre-issue-188 state file. A
    work item already in flight was never offered the choice, so it made none,
    and the opt-in node it never saw is skipped rather than blocking it."""
    WorkItemState.path_for(tmp_path).write_text(
        json.dumps({"workItem": "issue-1", "currentNode": "design"}), encoding="utf-8"
    )
    state = WorkItemState.load(tmp_path, "issue-1")
    assert state.opt_ins == {}
    assert state.current_node == "design"


# -- the rename, and what it must not break (issue-365, decision-127) -----------


def test_the_file_is_work_item_state_json(tmp_path):
    WorkItemState(work_item="issue-1").save(tmp_path)
    assert (tmp_path / STATE_FILENAME).is_file()
    assert STATE_FILENAME == "work-item-state.json"
    assert not (tmp_path / LEGACY_STATE_FILENAME).exists()


def test_a_work_item_mid_flight_keeps_its_pointer_across_the_rename(tmp_path):
    """The upgrade needs no migration step: a state file written under the old
    name is read, and the next save writes the current one."""
    (tmp_path / LEGACY_STATE_FILENAME).write_text(
        json.dumps({"workItem": "issue-1", "currentNode": "implementation"}),
        encoding="utf-8",
    )
    state = WorkItemState.load(tmp_path, "issue-1")
    assert state.current_node == "implementation"

    state.save(tmp_path)
    assert (tmp_path / STATE_FILENAME).is_file()
    # The old file is KEPT, never deleted: it is the operator's record, and a
    # rollback to the previous release must still find a pointer.
    assert (tmp_path / LEGACY_STATE_FILENAME).is_file()


def test_the_current_name_wins_when_both_are_present(tmp_path):
    (tmp_path / LEGACY_STATE_FILENAME).write_text(
        json.dumps({"workItem": "issue-1", "currentNode": "design"}), encoding="utf-8"
    )
    WorkItemState(work_item="issue-1", current_node="verification").save(tmp_path)
    assert WorkItemState.load(tmp_path, "issue-1").current_node == "verification"


def test_state_serialises_the_declared_repositories(tmp_path):
    state = WorkItemState(work_item="issue-1")
    state.repos = ["octo/app", "octo/infra"]
    state.save(tmp_path)
    assert WorkItemState.load(tmp_path, "issue-1").repos == ["octo/app", "octo/infra"]


def test_a_state_file_without_repos_declares_nothing(tmp_path):
    (tmp_path / STATE_FILENAME).write_text(
        json.dumps({"workItem": "issue-1"}), encoding="utf-8"
    )
    assert WorkItemState.load(tmp_path, "issue-1").repos == []
