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


# -- the work item's pull requests (issue-368) ---------------------------------


def test_a_pull_request_is_recorded_with_everything_the_repository_knows(tmp_path):
    """R2.1 — the entry is the pull request, not a pointer to somewhere local."""
    state = WorkItemState(work_item="github:octo/app#15")
    entry = state.link_pr(
        "github:octo/lib#7",
        repository="octo/lib",
        number=7,
        url="https://github.com/octo/lib/pull/7",
        linked_by="session",
    )
    assert entry is not None
    assert entry.state == "open" and entry.linked_by == "session" and entry.linked_at
    # The inner loop's directory is derived, so a reader needs no code to find it.
    assert entry.state_dir == "pr-loops/octo__lib/pr-7"
    state.save(tmp_path)
    reloaded = WorkItemState.load(tmp_path, "github:octo/app#15")
    assert [pr.ref for pr in reloaded.pull_requests] == ["github:octo/lib#7"]
    carried = reloaded.pull_request("github:octo/lib#7")
    assert carried is not None and carried.url.endswith("/pull/7")


def test_a_pull_request_in_the_work_items_own_repository_keeps_the_shipped_layout(
    tmp_path,
):
    """issue-183's two layouts, derived rather than guessed."""
    state = WorkItemState(work_item="github:octo/app#15")
    own = state.link_pr("github:octo/app#16", repository="octo/app", number=16)
    assert own is not None and own.state_dir == "pr-loops/pr-16"
    state.save(tmp_path)
    # …and it survives a reload, which cannot re-derive `origin` from the id alone.
    reloaded = WorkItemState.load(tmp_path, "github:octo/app#15")
    carried = reloaded.pull_request("github:octo/app#16")
    assert carried is not None and carried.state_dir == "pr-loops/pr-16"


def test_linking_a_pull_request_is_idempotent_by_ref(tmp_path):
    """R2.1 — two writers, one fact: a comment must not grow the list."""
    state = WorkItemState(work_item="github:octo/app#15")
    assert state.link_pr("github:octo/lib#7", repository="octo/lib", number=7)
    assert state.link_pr("github:octo/lib#7", repository="octo/lib", number=7) is None
    assert state.link_pr("github:octo/app#15", repository="octo/app", number=15) is None
    assert len(state.pull_requests) == 1


def test_a_pull_requests_upstream_state_is_recorded_on_its_own_entry(tmp_path):
    """R2.2 — merged/closed is the repository's fact about that pull request."""
    state = WorkItemState(work_item="github:octo/app#15")
    state.link_pr("github:octo/lib#7", repository="octo/lib", number=7)
    state.link_pr("github:octo/infra#3", repository="octo/infra", number=3)
    assert state.set_pr_state("github:octo/lib#7", "merged") is not None
    assert state.set_pr_state("github:octo/lib#7", "exploded") is None
    assert state.set_pr_state("github:nope/x#1", "merged") is None
    merged = state.pull_request("github:octo/lib#7")
    still_open = state.pull_request("github:octo/infra#3")
    assert merged is not None and merged.state == "merged"
    assert still_open is not None and still_open.state == "open"


def test_an_unusable_pull_request_entry_is_skipped_and_the_rest_honoured(tmp_path):
    """Abuse case — this file is proposable by anyone who can open a pull request.

    A `repository` that is not a usable repository path becomes a directory name,
    so it is refused; the entry is dropped and the file's other entries stand.
    """
    (tmp_path / "work-item-state.json").write_text(
        json.dumps(
            {
                "workItem": "github:octo/app#15",
                "pullRequests": [
                    {"ref": "github:octo/lib#7", "repository": "../etc", "number": 7},
                    {
                        "ref": "github:octo/app#16",
                        "repository": "octo/app",
                        "number": 16,
                    },
                    {"ref": "", "repository": "octo/x", "number": 1},
                ],
            }
        ),
        encoding="utf-8",
    )
    state = WorkItemState.load(tmp_path, "github:octo/app#15")
    assert [pr.ref for pr in state.pull_requests] == ["github:octo/app#16"]


def test_a_forged_state_dir_is_refused_and_recomputed(tmp_path):
    """Abuse case — a path this repository's own rules did not build."""
    (tmp_path / "work-item-state.json").write_text(
        json.dumps(
            {
                "workItem": "github:octo/app#15",
                "pullRequests": [
                    {
                        "ref": "github:octo/lib#7",
                        "repository": "octo/lib",
                        "number": 7,
                        "stateDir": "../../../etc/cron.d",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    state = WorkItemState.load(tmp_path, "github:octo/app#15")
    assert state.pull_requests[0].state_dir == "pr-loops/octo__lib/pr-7"


def test_the_frozen_choices_round_trip(tmp_path):
    """R4.1 — the work item's own file says what it runs on."""
    state = WorkItemState(work_item="github:octo/app#15")
    state.session_per_pr, state.model, state.effort = "always", "opus-5", "high"
    state.save(tmp_path)
    reloaded = WorkItemState.load(tmp_path, "github:octo/app#15")
    assert reloaded.session_per_pr == "always"
    assert reloaded.model == "opus-5" and reloaded.effort == "high"
    # "" is *no choice*, which is a different fact from "the operator's default".
    assert WorkItemState(work_item="x").session_per_pr == ""


def test_a_legacy_session_block_is_never_read_and_never_rewritten(tmp_path):
    """R3.1, R3.3 — a harness conversation id in a repository is nobody's to resume."""
    path = tmp_path / "work-item-state.json"
    path.write_text(
        json.dumps(
            {
                "workItem": "github:octo/app#15",
                "currentNode": "design",
                "session": {"id": "somebody-elses", "runner": "tmux", "alive": True},
            }
        ),
        encoding="utf-8",
    )
    state = WorkItemState.load(tmp_path, "github:octo/app#15")
    assert not hasattr(state, "session")
    assert state.current_node == "design"  # everything else still loads
    state.save(tmp_path)
    assert "somebody-elses" not in path.read_text(encoding="utf-8")
