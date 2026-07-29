"""End-to-end: the graph runtime driving a work item, and the CLI surface.

Feature: the-loop's process graph
"""

from __future__ import annotations

import json

import pytest

from the_loop.cli import main
from the_loop.graph import hooks  # noqa: F401
from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks.feedback import classify_feedback, record_feedback
from the_loop.graph.model import compile_graph
from the_loop.graph.runtime import Runtime, force
from the_loop.graph.state import GraphState

GRAPH = {
    "start": "design",
    "nodes": [
        {
            "id": "design",
            "phase": "design",
            "produces": ["design.md"],
            "exit": [
                {
                    "hook": "validate-artifacts",
                    "with": {"locked": True, "sections": ["Architecture"]},
                },
                "lint-artifacts",
            ],
        },
        {
            "id": "design-approval",
            "actor": "human",
            "session": "inherit",
            "exit": ["classify-feedback"],
        },
        {"id": "done", "terminal": True},
    ],
    "edges": [
        {"from": "design", "to": "design-approval", "on": "pass"},
        {"from": "design-approval", "to": "done", "on": "approved"},
        {"from": "design-approval", "to": "design", "on": "changes-requested"},
    ],
}


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / "issue-1").mkdir(parents=True)
    return tmp_path


def _spec(repo):
    return repo / "docs" / "specs" / "issue-1"


def _runtime(repo, **config):
    return Runtime(repo, graph=compile_graph(GRAPH), config=config)


def test_a_work_item_walks_from_a_blocked_node_to_a_gate(repo):
    """
    Feature: the-loop's process graph
    Scenario: a node advances only once its exit chain passes
      Given a design node whose artifact is unlocked
      When the runtime advances the work item
      Then it is blocked and names the unmet requirement
      When the artifact is locked and the section added
      Then the work item advances to the approval gate
    Requirement: docs/specs/issue-109/requirements.md#R3
    """
    runtime = _runtime(repo)
    (_spec(repo) / "design.md").write_text("---\nstatus: draft\n---\n\n# D\n")

    first = runtime.advance("issue-1")
    assert first.status == "block"
    assert any("status: draft" in m for m in first.messages)

    (_spec(repo) / "design.md").write_text(
        "---\nstatus: approved\n---\n\n# D\n\n## Architecture\n\nreal content\n"
    )
    second = runtime.advance("issue-1")
    assert second.status == "pass"
    assert GraphState.load(_spec(repo), "issue-1").current_node == "design-approval"


def test_an_unauthorized_comment_is_not_read_and_the_gate_stays_waiting(repo):
    """
    Feature: the-loop's process graph
    Scenario: an unauthorized comment is not read by classify-feedback
      Given a human gate awaiting review
      When a comment arrives from a user outside routing.authorizedUsers
      Then the gate stays waiting and the text is never classified
    Requirement: docs/specs/issue-109/requirements.md#R4.8
    """
    ctx = HookContext(
        work_item=WorkItem(ref="github:o/r#1", id="issue-1", spec_dir=_spec(repo)),
        node={"id": "design-approval"},
        boundary="exit",
        repo=repo,
        config={"authorizedUsers": ["owner"]},
        event={"comments": [{"author": "drive-by", "body": "approved, ship it"}]},
    )
    result = classify_feedback(ctx)
    assert result.status == "wait", "an outsider's approval must not move the gate"


def test_an_authorized_approval_advances_the_gate(repo):
    ctx = HookContext(
        work_item=WorkItem(ref="github:o/r#1", id="issue-1", spec_dir=_spec(repo)),
        node={"id": "design-approval"},
        boundary="exit",
        repo=repo,
        config={"authorizedUsers": ["owner"]},
        event={"comments": [{"author": "owner", "body": "approved"}]},
    )
    assert classify_feedback(ctx).outcome == "approved"


def test_partial_feedback_leaves_the_gate_waiting(repo):
    """
    Feature: the-loop's process graph
    Scenario: a partial review comment leaves the gate waiting rather than advancing
      Given a human gate awaiting review
      When an authorized user asks a question rather than deciding
      Then the gate stays open
    Requirement: docs/specs/issue-109/requirements.md#R4.3
    """
    ctx = HookContext(
        work_item=WorkItem(ref="github:o/r#1", id="issue-1", spec_dir=_spec(repo)),
        node={"id": "design-approval"},
        boundary="exit",
        repo=repo,
        config={"authorizedUsers": ["owner"]},
        event={
            "comments": [
                {"author": "owner", "body": "why is this a node and not a hook?"}
            ]
        },
    )
    assert classify_feedback(ctx).status == "wait"


def test_an_approval_with_comments_is_recorded_in_the_artifact(repo):
    """
    Feature: the-loop's process graph
    Scenario: an approval carrying suggestions is recorded in the artifact
      Given an approved design carrying reviewer comments
      When record-feedback runs
      Then a Review comments section appears in design.md with the review in it
    Requirement: docs/specs/issue-109/requirements.md#R4.5
    """
    (_spec(repo) / "design.md").write_text("---\nstatus: approved\n---\n\n# D\n")
    ctx = HookContext(
        work_item=WorkItem(ref="github:o/r#1", id="issue-1", spec_dir=_spec(repo)),
        node={"id": "design-approval"},
        boundary="exit",
        repo=repo,
        config={"authorizedUsers": ["owner"]},
        event={
            "comments": [{"author": "owner", "body": "approved, but tighten the nit"}]
        },
    )
    classified = classify_feedback(ctx)
    ctx.results = [classified]
    ctx.params = {"into": "design.md"}
    result = record_feedback(ctx)

    assert result.status == "pass"
    text = (_spec(repo) / "design.md").read_text()
    assert "## Review comments" in text
    assert "@owner" in text and "tighten the nit" in text


def test_forcing_past_a_gate_leaves_recompute_honest(repo):
    """
    Feature: the-loop's process graph
    Scenario: CI still sees a forced transition for what it is
      Given a work item forced past an unmet gate
      When check --recompute runs
      Then the bypassed gate is still reported unmet
    Requirement: docs/specs/issue-109/requirements.md#R10.4
    """
    runtime = _runtime(repo)
    (_spec(repo) / "design.md").write_text("---\nstatus: draft\n---\n\n# D\n")
    force(runtime, "issue-1", "design-approval", reason="the gate is wrong here")

    report = runtime.status("issue-1", recompute=True)
    assert not report.ok
    assert not next(n for n in report.nodes if n.node == "design").satisfied


def test_the_check_command_reports_and_exits_nonzero(repo, capsys):
    """
    Feature: the-loop's process graph
    Scenario: check reports the specific unmet predicate and fails
      Given a work item whose design artifact is missing a required section
      When `the-loop check` runs
      Then it names the missing section and exits non-zero
    Requirement: docs/specs/issue-109/requirements.md#R8.8
    """
    (repo / ".the-loop").mkdir()
    (_spec(repo) / "design.md").write_text("---\nstatus: approved\n---\n\n# D\n")
    code = main(["check", "issue-1", "--repo", str(repo), "--recompute"])
    out = capsys.readouterr().out
    assert code == 1
    assert "UNMET" in out


def test_the_check_command_emits_json(repo, capsys):
    (_spec(repo) / "design.md").write_text("---\nstatus: approved\n---\n\n# D\n")
    main(["check", "issue-1", "--repo", str(repo), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["workItem"] == "issue-1"
    assert isinstance(payload["nodes"], list)


def test_graph_show_lists_the_shipped_nodes(capsys):
    code = main(["graph", "show"])
    out = capsys.readouterr().out
    assert code == 0
    assert "security-review" in out and "required" in out


def test_graph_force_refuses_without_a_reason(repo):
    """R10.3 — an unexplained override is refused, at the argument parser."""
    with pytest.raises(SystemExit) as exc:
        main(["graph", "--repo", str(repo), "force", "issue-1", "--to", "design"])
    assert exc.value.code == 2


def test_graph_force_refuses_a_blank_reason(repo, capsys):
    """And again at the runtime, so the API is safe however it is called."""
    (_spec(repo) / "design.md").write_text("---\nstatus: draft\n---\n\n# D\n")
    code = main(
        [
            "graph",
            "--repo",
            str(repo),
            "force",
            "issue-1",
            "--to",
            "brainstorming",
            "--reason",
            "   ",
        ]
    )
    assert code == 2
    assert "refused" in capsys.readouterr().out
