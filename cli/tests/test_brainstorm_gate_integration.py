"""The brainstorm waits for its author's approval (issue-494).

Walked on the SHIPPED outer loop with real hook chains over a temporary spec
directory, because the defect was the graph's: `brainstorming` passed on shape
alone and its `pass` edge went straight to `requirements-definition`, so the
author's first reply was the last one the brainstorm received.
"""

from __future__ import annotations

import json

import pytest

from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.frontmatter import read_front_matter
from the_loop.graph.model import load_graph
from the_loop.graph.runtime import Runtime
from the_loop.graph.state import WorkItemState

WORK_ITEM = "issue-1"

BRAINSTORM = (
    "---\ntype: brainstorm\nphase: brainstorming\nstatus: draft\napprovedBy: []\n"
    "---\n\n# Brainstorm: x\n\n## Problem / opportunity\n\nreal\n\n"
    "## Open questions\n\nnone\n"
)


class _FakeGitHub:
    def __init__(self):
        self.posted = []

    def call(self, op, **params):
        if op == "add-comment":
            self.posted.append(str(params.get("body") or ""))
        if op == "list-comments":
            return {"comments": []}
        return {}


@pytest.fixture()
def github(monkeypatch):
    provider = _FakeGitHub()
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve", lambda target, config: provider
    )
    return provider


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    return tmp_path


def _spec(repo):
    return repo / "docs" / "specs" / WORK_ITEM


def _at_brainstorming(repo, skips=None):
    state = {
        "workItem": WORK_ITEM,
        "currentNode": "brainstorming",
        "decisions": {"phase-selection": {"at": "2026-10-16T00:00:00Z"}},
        "skips": skips or {},
    }
    (_spec(repo) / "work-item-state.json").write_text(json.dumps(state))


def _runtime(repo):
    return Runtime(repo, graph=load_graph(), config={"authorizedUsers": ["owner"]})


def _reply(*bodies, author="owner"):
    return {"comments": [{"author": author, "body": b} for b in bodies]}


def _node(repo):
    return WorkItemState.load(_spec(repo), WORK_ITEM).current_node


def test_a_written_brainstorm_waits_at_its_gate_across_comments(repo, github):
    """
    Feature: the brainstorm's approval gate
    Scenario: questions and remarks do not move the brainstorm on
      Given a work item at brainstorming with brainstorm.md written
      When the session completes brainstorming
      Then the work item is parked at brainstorm-approval, not requirements
      When the author asks a question, then remarks on an option
      Then the gate stays open after each
      When someone outside authorizedUsers replies "approved"
      Then the gate still stays open
    Requirement: docs/specs/issue-494/bugfix.md R1.1, R1.2, R1.5, R1.6
    """
    _at_brainstorming(repo)
    (_spec(repo) / "brainstorm.md").write_text(BRAINSTORM)
    runtime = _runtime(repo)

    report = runtime.advance(WORK_ITEM)
    assert report.status == "pass"
    assert _node(repo) == "brainstorm-approval"
    assert any("brainstorm-approval" in body for body in github.posted)

    for event in (
        _reply("what would option B cost us?"),
        _reply("I'd lean towards the second option, thinking it over"),
        _reply("approved", author="drive-by"),
    ):
        assert runtime.advance(WORK_ITEM, event=event).status == "wait"
        assert _node(repo) == "brainstorm-approval"
    assert read_front_matter(_spec(repo) / "brainstorm.md")["status"] == "draft"


def test_an_approval_locks_the_brainstorm_and_moves_to_requirements(repo, github):
    """
    Feature: the brainstorm's approval gate
    Scenario: the author's approval locks brainstorm.md and opens requirements
      Given a work item parked at brainstorm-approval
      When an authorized user approves
      Then brainstorm.md records the review and the approver, status approved
      And the work item is at requirements-definition
    Requirement: docs/specs/issue-494/bugfix.md R1.3
    """
    _at_brainstorming(repo)
    (_spec(repo) / "brainstorm.md").write_text(BRAINSTORM)
    runtime = _runtime(repo)
    runtime.advance(WORK_ITEM)

    report = runtime.advance(WORK_ITEM, event=_reply("approved"))
    assert report.outcome == "approved"
    assert _node(repo) == "requirements-definition"
    front = read_front_matter(_spec(repo) / "brainstorm.md")
    assert front["status"] == "approved"
    assert front["approvedBy"] == ["owner"]
    assert "## Review comments" in (_spec(repo) / "brainstorm.md").read_text()


def test_changes_requested_returns_to_brainstorming(repo, github):
    """
    Feature: the brainstorm's approval gate
    Scenario: the author asks for changes
      Given a work item parked at brainstorm-approval
      When an authorized user requests changes
      Then the work item is back at brainstorming, brainstorm.md unlocked
    Requirement: docs/specs/issue-494/bugfix.md R1.4
    """
    _at_brainstorming(repo)
    (_spec(repo) / "brainstorm.md").write_text(BRAINSTORM)
    runtime = _runtime(repo)
    runtime.advance(WORK_ITEM)

    report = runtime.advance(WORK_ITEM, event=_reply("changes requested: add C"))
    assert report.outcome == "changes-requested"
    assert _node(repo) == "brainstorming"
    assert read_front_matter(_spec(repo) / "brainstorm.md")["status"] == "draft"


def test_no_brainstorm_goes_straight_to_requirements(repo, github):
    """
    Feature: the brainstorm's approval gate
    Scenario: a work item whose scope was already clear is not held
      Given a work item at brainstorming that wrote no brainstorm.md
      When the session completes brainstorming
      Then the work item is at requirements-definition, never at the gate
      And no review was requested
    Requirement: docs/specs/issue-494/bugfix.md R2.1
    """
    _at_brainstorming(repo)
    report = _runtime(repo).advance(WORK_ITEM)
    assert report.outcome == "not-entered"
    assert _node(repo) == "requirements-definition"
    state = WorkItemState.load(_spec(repo), WORK_ITEM)
    assert "brainstorm-approval" not in state.nodes
    assert not any("brainstorm-approval" in body for body in github.posted)


def test_declaring_the_gate_away_restores_the_old_route(repo, github):
    """
    Feature: the brainstorm's approval gate
    Scenario: brainstorm-approval alone is declared skipped
      Given a work item at brainstorming whose author declared the gate away
      When the session completes a written brainstorm
      Then the work item is at requirements-definition, the gate recorded skipped
    Requirement: docs/specs/issue-494/bugfix.md R2.3
    """
    _at_brainstorming(
        repo,
        skips={"brainstorm-approval": {"by": "@owner", "reason": "clear scope"}},
    )
    (_spec(repo) / "brainstorm.md").write_text(BRAINSTORM)
    report = _runtime(repo).advance(WORK_ITEM)
    assert report.outcome == "pass"
    assert _node(repo) == "requirements-definition"
    state = WorkItemState.load(_spec(repo), WORK_ITEM)
    assert state.nodes["brainstorm-approval"].outcome == "skipped"


def test_a_skipped_brainstorm_never_reaches_its_gate(repo, github):
    """
    Feature: the brainstorm's approval gate
    Scenario: brainstorming is declared skipped
      Given a work item whose author declared brainstorming away
      Then its skipped edge lands on requirements-definition, past the gate
      And `check --recompute` does not report the gate as unmet
    Requirement: docs/specs/issue-494/bugfix.md R2.2
    """
    graph = load_graph()
    assert graph.next_node("brainstorming", "skipped") == "requirements-definition"

    _at_brainstorming(
        repo, skips={"brainstorming": {"by": "@owner", "reason": "clear scope"}}
    )
    report = _runtime(repo).status(WORK_ITEM, recompute=True)
    gate = next(n for n in report.nodes if n.node == "brainstorm-approval")
    assert gate.status in ("pass", "skip"), gate.messages


def test_deleting_the_brainstorm_at_its_gate_does_not_open_it(repo, github):
    """
    Feature: the brainstorm's approval gate
    Scenario: brainstorm.md disappears while its gate is open
      Given a work item parked at brainstorm-approval
      When brainstorm.md is deleted and the gate is evaluated, with or without a reply
      Then the gate blocks and names the missing brainstorm
      And the work item does not reach requirements without a human approval
    Requirement: docs/specs/issue-494/bugfix.md R1.2, R1.5 (self-review S2)
    """
    _at_brainstorming(repo)
    (_spec(repo) / "brainstorm.md").write_text(BRAINSTORM)
    runtime = _runtime(repo)
    runtime.advance(WORK_ITEM)
    (_spec(repo) / "brainstorm.md").unlink()

    # The first evaluation blocks; the identical second one escalates to a
    # human (a repeated block). Neither opens the gate.
    for event, status in ((None, "block"), (_reply("any thoughts?"), "escalated")):
        report = runtime.advance(WORK_ITEM, event=event)
        assert report.status == status, report
        assert any("brainstorm.md" in m for m in report.messages)
        assert _node(repo) == "brainstorm-approval"


def test_deleting_the_brainstorm_after_changes_requested_does_not_skip_them(
    repo, github
):
    """
    Feature: the brainstorm's approval gate
    Scenario: the brainstorm is deleted instead of revised
      Given a work item sent back to brainstorming by changes-requested
      When brainstorm.md is deleted and brainstorming is completed
      Then brainstorming blocks rather than routing around the gate
    Requirement: docs/specs/issue-494/bugfix.md R1.4, R1.5 (self-review S2)
    """
    _at_brainstorming(repo)
    (_spec(repo) / "brainstorm.md").write_text(BRAINSTORM)
    runtime = _runtime(repo)
    runtime.advance(WORK_ITEM)
    runtime.advance(WORK_ITEM, event=_reply("changes requested: add C"))
    assert _node(repo) == "brainstorming"
    (_spec(repo) / "brainstorm.md").unlink()

    report = runtime.advance(WORK_ITEM)
    assert report.status == "block", report
    assert any("brainstorm.md" in m for m in report.messages)
    assert _node(repo) == "brainstorming"


def test_a_skipped_brainstorm_left_on_disk_is_not_reported_at_its_gate(repo, github):
    """
    Feature: the brainstorm's approval gate
    Scenario: brainstorming declared skipped, but a brainstorm.md is on disk
      Given a work item whose author declared brainstorming away
      And a brainstorm.md left in its spec directory
      Then `check --recompute` does not report brainstorm-approval as waiting,
      because the walk routes past a gate whose authoring node was skipped
    Requirement: docs/specs/issue-494/bugfix.md R2.2 (critic finding C1)
    """
    _at_brainstorming(
        repo, skips={"brainstorming": {"by": "@owner", "reason": "clear scope"}}
    )
    (_spec(repo) / "brainstorm.md").write_text(BRAINSTORM)
    report = _runtime(repo).status(WORK_ITEM, recompute=True)
    gate = next(n for n in report.nodes if n.node == "brainstorm-approval")
    assert gate.status in ("pass", "skip"), gate.messages
