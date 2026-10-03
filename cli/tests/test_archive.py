"""A work item's terminal record, and `check` reading it (issue-452).

Unit tests for :mod:`the_loop.archive` and for the archived branch of
:func:`the_loop.core.graphs.check`. Every runtime here is a real one over the
shipped `pdlc-work-item-loop` and a real `work-item-state.json` under
``tmp_path``; the portable record is a real :class:`WorkItemStore` file.

Requirement: docs/specs/issue-452/bugfix.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from the_loop import archive
from the_loop.core import graphs
from the_loop.graph.bootstrap import build_runtime
from the_loop.workitem import ENDED, WorkItemStore

REF = "github:octo/repo#3"
ITEM = "issue-3"


def _state(root: Path, **fields) -> Path:
    spec = root / "docs" / "specs" / ITEM
    spec.mkdir(parents=True, exist_ok=True)
    data = {"workItem": ITEM, "currentNode": "", "nodes": {}}
    data.update(fields)
    (spec / "work-item-state.json").write_text(json.dumps(data))
    return spec


def _runtime(root: Path):
    return build_runtime(root, spec_root="docs/specs", origin_repo="octo/repo")


COMPLETED_STATE = {
    "currentNode": "complete",
    "phase": "complete",
    "nodes": {
        "phase-selection": {"outcome": "selected", "attempts": 1},
        "implementation": {"outcome": "pass", "attempts": 1},
        "complete": {
            "outcome": "pass",
            "attempts": 1,
            "enteredAt": "2026-10-02T22:29:00+00:00",
            "exitedAt": "2026-10-02T22:29:41+00:00",
        },
    },
    "skips": {
        "brainstorming": {"via": "phase-selection", "by": "octocat"},
        "requirements-definition": {"via": "phase-selection", "by": "octocat"},
        # Forged: phase-selection is required, and "made-up" is no node at all.
        "phase-selection": {"via": "hand-edit"},
        "made-up": {"via": "hand-edit"},
    },
    "optIns": {"design-critic-review": {"via": "phase-selection", "by": "octocat"}},
    "harness": "codex",
    "model": "gpt-5",
    "effort": "high",
    "pullRequests": [
        {
            "ref": "github:octo/repo#4",
            "url": "https://evil.example/phish",
            "state": "merged",
        },
        {"ref": "not a ref", "url": "https://evil.example/2", "state": "open"},
    ],
}


# -- terminal_record ---------------------------------------------------------------


def test_a_claimed_completion_node_is_recorded_as_completed(tmp_path):
    """
    Feature: the terminal record
      Scenario: a work item whose session claimed `complete`
        Given a state file whose `complete` record carries an outcome
        When the terminal record is read
        Then it says completed, when, and what the item froze and delivered

    Requirement: docs/specs/issue-452/bugfix.md R1.1, R1.2
    """
    spec = _state(tmp_path, **COMPLETED_STATE)
    (spec / "evidence").mkdir()
    (spec / "evidence" / "verification.md").write_text("ok")
    (spec / "evidence" / "screens").mkdir()
    (spec / "evidence" / "screens" / "one.png").write_bytes(b"\x89PNG")

    record = archive.terminal_record(_runtime(tmp_path), ITEM)

    assert record is not None
    assert record["workItem"] == ITEM
    assert record["loop"] == "pdlc-work-item-loop"
    assert (record["node"], record["phase"]) == ("complete", "complete")
    assert record["completed"] is True
    assert record["completedAt"] == "2026-10-02T22:29:41+00:00"
    selections = record["selections"]
    assert selections["skipped"] == ["brainstorming", "requirements-definition"]
    assert selections["optedIn"] == ["design-critic-review"]
    assert (selections["harness"], selections["model"], selections["effort"]) == (
        "codex",
        "gpt-5",
        "high",
    )
    assert record["pullRequests"] == [
        {
            "ref": "github:octo/repo#4",
            "url": "https://github.com/octo/repo/issues/4",
            "state": "merged",
        }
    ]
    assert record["specDir"] == "docs/specs/issue-3"
    assert record["evidence"] == ["screens/one.png", "verification.md"]
    assert record["recordedAt"]


def test_a_mid_flight_item_is_not_completed(tmp_path):
    """R1.3 — a pointer short of `complete` is never read as completion."""
    _state(
        tmp_path,
        currentNode="human-approval",
        nodes={"human-approval": {"attempts": 1}},
    )

    record = archive.terminal_record(_runtime(tmp_path), ITEM)

    assert record is not None
    assert record["node"] == "human-approval"
    assert record["completed"] is False
    assert record["completedAt"] == ""


def test_an_entered_but_unclaimed_complete_is_not_completed(tmp_path):
    """R1.3 — `finish-tasks` entered, the claim never made: not completed."""
    _state(tmp_path, currentNode="complete", nodes={"complete": {"attempts": 1}})

    record = archive.terminal_record(_runtime(tmp_path), ITEM)

    assert record is not None and record["completed"] is False


def test_cleanup_after_complete_still_reads_as_completed(tmp_path):
    """The `cleanup` node follows `complete`; the claim on `complete` still counts."""
    _state(
        tmp_path,
        currentNode="cleanup",
        nodes={
            "complete": {"outcome": "pass", "exitedAt": "2026-10-02T22:29:41+00:00"},
            "cleanup": {"attempts": 1},
        },
    )

    record = archive.terminal_record(_runtime(tmp_path), ITEM)

    assert record is not None and record["completed"] is True


def test_no_state_file_is_no_record(tmp_path):
    (tmp_path / "docs" / "specs" / ITEM).mkdir(parents=True)

    assert archive.terminal_record(_runtime(tmp_path), ITEM) is None


def test_abuse_forged_fields_are_filtered(tmp_path):
    """
    Feature: the terminal record is a filtered copy of an agent-writable file
      Scenario: a hand-edited state file
        Given a node id the graph lacks, an over-long model and hostile evidence names
        When the terminal record is read
        Then the node is dropped, the model is dropped and only plain names are kept

    Requirement: docs/specs/issue-452/bugfix.md § Security considerations
    """
    spec = _state(
        tmp_path,
        currentNode="not-a-node",
        model="x" * 500,
        effort="high\x1b[2J",
        nodes={"complete": {"outcome": "pass", "exitedAt": "\x1b]0;pwned\x07"}},
    )
    evidence = spec / "evidence"
    evidence.mkdir()
    (evidence / "ok.md").write_text("ok")
    (evidence / "bad\x1b[31m.md").write_text("no")
    (evidence / "spaced name.md").write_text("no")
    for n in range(60):
        (evidence / f"z{n:02d}.md").write_text("x")

    record = archive.terminal_record(_runtime(tmp_path), ITEM)

    assert record is not None
    assert record["node"] == ""
    assert record["selections"]["model"] == ""
    assert record["selections"]["effort"] == ""
    assert "ok.md" in record["evidence"]
    assert all("\x1b" not in name and " " not in name for name in record["evidence"])
    assert len(record["evidence"]) == archive.MAX_EVIDENCE
    assert record["completed"] is True and record["completedAt"] == ""


def test_abuse_a_symlinked_evidence_directory_is_not_walked(tmp_path):
    """An `evidence -> /` link must not list, or walk, anything outside the spec."""
    spec = _state(tmp_path, currentNode="design")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("x")
    (spec / "evidence").symlink_to(outside, target_is_directory=True)

    record = archive.terminal_record(_runtime(tmp_path), ITEM)

    assert record is not None and record["evidence"] == []


def test_a_large_evidence_tree_is_walked_only_so_far(tmp_path, monkeypatch):
    spec = _state(tmp_path, currentNode="design")
    evidence = spec / "evidence"
    for d in range(30):
        sub = evidence / f"d{d:02d}"
        sub.mkdir(parents=True)
        for n in range(10):
            (sub / f"f{n}.md").write_text("x")
    monkeypatch.setattr(archive, "_MAX_VISITED", 25)

    record = archive.terminal_record(_runtime(tmp_path), ITEM)

    assert record is not None
    assert 0 < len(record["evidence"]) < 300


# -- the outcome -------------------------------------------------------------------


@pytest.mark.parametrize(
    "terminal, cancelled, expected",
    [
        ({"completed": True}, False, archive.COMPLETED),
        ({"completed": True}, True, archive.COMPLETED),
        ({"completed": False}, True, archive.CANCELLED),
        ({"completed": False}, False, archive.CLOSED_EXTERNALLY),
        (None, True, archive.CANCELLED),
        (None, False, archive.UNKNOWN),
    ],
)
def test_the_outcome_never_infers_completion_from_the_closure(
    terminal, cancelled, expected
):
    """R1.2, R1.3 — only a recorded claim is completion."""
    assert archive.closure_outcome(terminal, cancelled) == expected


@pytest.mark.parametrize(
    "event, payload, reason, expected",
    [
        ("issues", {"issue": {"state_reason": "not_planned"}}, "issue-closed", True),
        ("issues", {"issue": {"state_reason": "completed"}}, "issue-closed", False),
        ("issues", {"issue": {}}, "issue-closed", False),
        ("issues", {"issue": {"state_reason": "NOT_PLANNED!"}}, "issue-closed", False),
        ("pull_request", {"pull_request": {}}, "pr-closed", True),
        ("pull_request", {"pull_request": {"merged": True}}, "pr-merged", False),
    ],
)
def test_cancellation_is_an_explicit_signal(event, payload, reason, expected):
    assert archive.cancelled(event, payload, reason) is expected


# -- check reads the archive -------------------------------------------------------


@pytest.fixture
def portable(tmp_path, monkeypatch) -> WorkItemStore:
    """A CLI config whose state root holds the portable records, selected for `check`."""
    root = tmp_path / "state"
    config = tmp_path / "cli-config.yaml"
    config.write_text(f'version: "0.11.0"\nstate:\n  root: {root}\n')
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(config))
    return WorkItemStore(root / "portable")


def _stamp(store: WorkItemStore, terminal=None, outcome="completed") -> None:
    stamp = {
        "state": "closed",
        "kind": "issue",
        "reason": "issue-closed",
        "source": "webhook",
        "actor": "octocat",
        "at": "2026-10-02T22:30:00Z",
    }
    if outcome:
        stamp["outcome"] = outcome
    if terminal is not None:
        stamp["terminal"] = terminal
    store.write_section(REF, ENDED, stamp)


def test_check_reports_an_ended_ref_as_archived(tmp_path, portable):
    """
    Feature: `check` after normal cleanup
      Scenario: a ref whose checkout is gone and whose closure was stamped
        Given an unrelated directory with no spec directory for the work item
        And a portable record whose `ended` stamp carries a terminal record
        When `check` runs on the ref there
        Then it reports the archived completion and evaluates no node

    Requirement: docs/specs/issue-452/bugfix.md R2.1
    """
    elsewhere = tmp_path / "devbox"
    elsewhere.mkdir()
    _stamp(portable, terminal={"node": "complete", "completed": True})

    report = graphs.check(str(elsewhere), REF)

    assert report["workItem"] == ITEM
    assert report["stateFound"] is False
    assert report["nodes"] == []
    assert (report["currentNode"], report["pointer"]) == ("complete", "complete")
    assert report["ok"] is True
    archived = report["archived"]
    assert archived["ref"] == REF
    assert (archived["outcome"], archived["detail"]) == ("completed", "recorded")
    assert (archived["state"], archived["reason"], archived["actor"]) == (
        "closed",
        "issue-closed",
        "octocat",
    )
    assert archived["terminal"]["node"] == "complete"


def test_a_stamp_from_before_the_change_is_archived_with_detail_unavailable(
    tmp_path, portable
):
    """
    Feature: `check` after normal cleanup
      Scenario: a stamp from before the change
        Given an `ended` stamp with the six issue-329 keys and no terminal record
        When `check` runs on the ref from an unrelated directory
        Then it says archived with detail unavailable, at no node, and not ok

    Requirement: docs/specs/issue-452/bugfix.md R2.2
    """
    _stamp(portable, outcome="")

    report = graphs.check(str(tmp_path), REF)

    assert report["archived"]["detail"] == "unavailable"
    assert report["archived"]["outcome"] == "unknown"
    assert "terminal" not in report["archived"]
    assert (report["currentNode"], report["pointer"], report["ok"]) == ("", "", False)
    assert report["nodes"] == []


def test_a_cancelled_item_is_archived_and_not_ok(tmp_path, portable):
    _stamp(
        portable, terminal={"node": "design", "completed": False}, outcome="cancelled"
    )

    report = graphs.check(str(tmp_path), REF)

    assert report["archived"]["outcome"] == "cancelled"
    assert (report["currentNode"], report["ok"]) == ("design", False)


def test_a_found_state_file_wins_over_the_archive(tmp_path, portable):
    """R2.3 — live state is never replaced by the archive."""
    _state(tmp_path, currentNode="implementation")
    _stamp(portable, terminal={"node": "complete", "completed": True})

    report = graphs.check(str(tmp_path), REF)

    assert "archived" not in report
    assert report["stateFound"] is True
    assert report["currentNode"] == "implementation"


def test_a_bare_id_does_not_consult_the_archive(tmp_path, portable):
    """R2.4 — the record is keyed by ref."""
    _stamp(portable, terminal={"node": "complete", "completed": True})

    report = graphs.check(str(tmp_path), ITEM)

    assert "archived" not in report
    assert report["currentNode"] == "phase-selection"


def test_recompute_over_an_existing_spec_directory_evaluates_the_artifacts(
    tmp_path, portable
):
    """R2.3 — `--recompute` in a checkout that has the artifacts still derives."""
    (tmp_path / "docs" / "specs" / ITEM).mkdir(parents=True)
    _stamp(portable, terminal={"node": "complete", "completed": True})

    report = graphs.check(str(tmp_path), REF, recompute=True)

    assert "archived" not in report
    assert report["nodes"]


def test_recompute_with_no_spec_directory_still_reads_the_archive(tmp_path, portable):
    _stamp(portable, terminal={"node": "complete", "completed": True})

    report = graphs.check(str(tmp_path), REF, recompute=True)

    assert report["archived"]["outcome"] == "completed"


def test_a_ref_that_never_ended_is_reported_as_before(tmp_path, portable):
    report = graphs.check(str(tmp_path), REF)

    assert "archived" not in report
    assert report["currentNode"] == "phase-selection"


def test_no_cli_config_means_no_archive(tmp_path, monkeypatch):
    """`check` in a CI checkout with no CLI config is unchanged."""
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "absent.yaml"))
    monkeypatch.chdir(tmp_path)

    report = graphs.check(str(tmp_path), REF)

    assert "archived" not in report


def test_a_malformed_terminal_value_reads_as_unavailable(tmp_path, portable):
    _stamp(portable, terminal="not a mapping")

    report = graphs.check(str(tmp_path), REF)

    assert report["archived"]["detail"] == "unavailable"
