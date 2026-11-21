"""A comment does not grade the node it arrives at (issue-551, Requirement 5).

Every inbound event used to run the pointer's exit chain as if the session had
claimed the node: a human's comment on a node still being worked on wrote
``lastBlock`` and emitted ``graph.blocked``, and a second comment repeated the
block and emitted ``graph.escalated``. These drive a *real* :class:`GraphLink`
with a *real* ``graph.Runtime`` over the shipped loops in a checkout under
``tmp_path`` — the entry points the dispatcher calls after every delivery.

Feature: An inbound event reads an agent-owned node, it does not grade it
Requirement: docs/specs/issue-551/requirements.md
"""

from __future__ import annotations

import subprocess

import pytest

from the_loop import eventlog
from the_loop.graph.bootstrap import build_runtime
from the_loop.graph.state import WorkItemState
from the_loop.sessions import SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent

REF = WorkItemRef.parse("github:octo/repo#113")
PR = WorkItemRef.parse("github:octo/repo#16")
ITEM = "issue-113"
REVIEWER = "octocat"
GRADES = {"graph.blocked", "graph.escalated", "graph.parked"}


class _FakeGitHub:
    """Answers the entry chains' calls, and reaches no network doing it."""

    def call(self, op, **params):
        return {"comments": []} if op == "list-comments" else {}


@pytest.fixture(autouse=True)
def github(monkeypatch):
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve", lambda target, config: _FakeGitHub()
    )


@pytest.fixture()
def events(monkeypatch):
    seen = []
    real = eventlog.emit

    def record(event, level="info", **fields):
        seen.append(event)
        return real(event, level=level, **fields)

    monkeypatch.setattr(eventlog, "emit", record)
    return seen


@pytest.fixture()
def checkout(tmp_path):
    """A real checkout of the work item's own repository, with its spec folder."""
    root = tmp_path / "checkout"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "remote",
            "add",
            "origin",
            "https://github.com/octo/repo.git",
        ],
        check=True,
    )
    (root / "docs" / "specs" / ITEM).mkdir(parents=True)
    return root


@pytest.fixture()
def link(tmp_path):
    return Dispatcher(
        registry=SessionRegistry(tmp_path / "sessions"),
        adapters={},
        config=RoutingConfig.from_mapping(
            {"authorizedUsers": [REVIEWER], "control": {"enabled": False}}, None
        ),
    ).graphlink


def _spec(checkout):
    return checkout / "docs" / "specs" / ITEM


def _stand_on(state_dir, node):
    state = WorkItemState.load(state_dir, ITEM)
    state.enter(node)
    state.save(state_dir)


def _state(state_dir):
    return WorkItemState.load(state_dir, ITEM)


def _comment(body, delivery="d-1"):
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id=delivery,
        work_items=[REF],
        payload={"comment": {"body": body, "user": {"login": REVIEWER}}},
    )


def test_a_comment_does_not_block_an_agent_node(link, checkout, events):
    """
    Feature: An inbound event reads an agent-owned node, it does not grade it
    Scenario: a comment does not block an agent node
      Given a work item whose pointer is on the agent-owned design node
      And design.md is not written, so the node's exit gate is unmet
      When two comments are delivered to its session
      Then no attempt is counted and no block is recorded
      And neither graph.blocked nor graph.escalated is in the event log
      And the status the session is shown is in-progress, not blocked

    Requirement: docs/specs/issue-551/requirements.md#R5.1
    Requirement: docs/specs/issue-551/requirements.md#R5.6
    """
    _stand_on(_spec(checkout), "design")
    before = (_spec(checkout) / "work-item-state.json").read_text()

    first = link.on_event(REF, str(checkout), _comment("how is it going?"))
    link.on_event(REF, str(checkout), _comment("any news?", delivery="d-2"))

    assert first is not None, "the graph was read; this is not a skip"
    record = _state(_spec(checkout)).nodes["design"]
    assert record.attempts == 1, "only entering the node counts an attempt"
    assert record.last_block == ""
    assert (_spec(checkout) / "work-item-state.json").read_text() == before
    assert not GRADES & set(events)
    context = link.context(REF, str(checkout))
    assert context.current_node == "design"
    assert context.status == "in-progress"


def test_a_met_exit_gate_still_advances_on_a_comment(link, checkout, events):
    """
    Feature: An inbound event reads an agent-owned node, it does not grade it
    Scenario: a met exit gate still advances on a comment
      Given a work item whose pointer is on the agent-owned self-review node
      And its evidence record is committed, so the node's exit gate is met
      When a comment is delivered to its session
      Then the work item advances exactly one node, as it did before

    Requirement: docs/specs/issue-551/requirements.md#R5.2
    """
    _stand_on(_spec(checkout), "self-review")
    evidence = _spec(checkout) / "evidence"
    evidence.mkdir()
    (evidence / "self-review.md").write_text("## Review cycles\n\none round\n")

    link.on_event(REF, str(checkout), _comment("thanks"))

    assert _state(_spec(checkout)).current_node == "critic-review"
    assert "graph.advanced" in events


def test_a_human_gate_still_classifies_the_comment_it_receives(link, checkout):
    """
    Feature: An inbound event reads an agent-owned node, it does not grade it
    Scenario: a human gate still classifies the comment it receives
      Given a work item parked at the human-owned requirements-approval node
      When an authorized reviewer comments "approved"
      Then classify-feedback reads the comment and the gate resolves

    Requirement: docs/specs/issue-551/requirements.md#R5.3
    """
    (_spec(checkout) / "requirements.md").write_text(
        "---\nstatus: approved\n---\n\n# R\n"
    )
    _stand_on(_spec(checkout), "requirements-approval")

    link.on_event(REF, str(checkout), _comment("approved"))

    assert _state(_spec(checkout)).current_node != "requirements-approval"


def test_a_human_gate_still_parks_on_a_comment_it_cannot_classify(
    link, checkout, events
):
    """
    Feature: An inbound event reads an agent-owned node, it does not grade it
    Scenario: a human gate still waits on a comment that is not an answer
      Given a work item at the human-owned requirements-approval node
      When an authorized reviewer comments something that is not a verdict
      Then the gate is evaluated with the comment and parks, as it did before

    Requirement: docs/specs/issue-551/requirements.md#R5.3
    """
    (_spec(checkout) / "requirements.md").write_text(
        "---\nstatus: approved\n---\n\n# R\n"
    )
    _stand_on(_spec(checkout), "requirements-approval")

    link.on_event(REF, str(checkout), _comment("let me read it tonight"))

    state = _state(_spec(checkout))
    assert state.current_node == "requirements-approval"
    assert state.parked and state.parked["node"] == "requirements-approval"
    assert "graph.parked" in events


def test_a_sessions_own_failing_claim_still_blocks_and_then_escalates(
    link, checkout, events
):
    """
    Feature: An inbound event reads an agent-owned node, it does not grade it
    Scenario: a session's own failing claim is still recorded, and a repeat escalates
      Given a work item whose pointer is on the agent-owned design node
      And design.md is not written
      When the session claims the node complete
      Then the block is recorded and graph.blocked is emitted
      And a comment delivered afterwards neither repeats the block nor escalates
      When the session claims the node complete again
      Then the repeated block escalates the node

    Requirement: docs/specs/issue-551/requirements.md#R5.4
    Requirement: docs/specs/issue-551/requirements.md#R5.5
    """
    _stand_on(_spec(checkout), "design")
    runtime = build_runtime(
        checkout, spec_root="docs/specs", authorized_users=[REVIEWER]
    )

    first = runtime.complete(ITEM, ref=REF.ref, node="design", actor="session")

    assert first["status"] == "block" and not first["moved"]
    assert "design.md" in _state(_spec(checkout)).nodes["design"].last_block
    assert events.count("graph.blocked") == 1
    assert link.context(REF, str(checkout)).status == "blocked"

    link.on_event(REF, str(checkout), _comment("any news?"))

    assert "graph.escalated" not in events, "a comment is not a second claim"
    assert events.count("graph.blocked") == 1

    second = runtime.complete(ITEM, ref=REF.ref, node="design", actor="session")

    assert second["status"] == "escalated"
    assert events.count("graph.escalated") == 1


def test_a_comment_does_not_block_a_pull_requests_inner_node(link, checkout, events):
    """
    Feature: An inbound event reads an agent-owned node, it does not grade it
    Scenario: a comment does not block an agent node of a pull request's inner loop
      Given a pull request whose inner loop stands on the agent-owned self-review node
      And its evidence record is not written, so the node's exit gate is unmet
      When two comments are delivered to the pull request's session
      Then no block is recorded in the inner loop's state
      And neither graph.blocked nor graph.escalated is in the event log
      And the status the pull request's session is shown is in-progress
      And the work item's own pointer is untouched

    Requirement: docs/specs/issue-551/requirements.md#R5.1
    Requirement: docs/specs/issue-551/requirements.md#R5.6
    """
    _stand_on(_spec(checkout), "implementation")
    inner = _spec(checkout) / "pr-loops" / "pr-16"
    inner.mkdir(parents=True)
    _stand_on(inner, "self-review")

    link.on_pr_event(REF, PR, str(checkout), _comment("how is it going?"))
    link.on_pr_event(REF, PR, str(checkout), _comment("any news?", delivery="d-2"))

    record = _state(inner).nodes["self-review"]
    assert record.attempts == 1
    assert record.last_block == ""
    assert not GRADES & set(events)
    context = link.pr_context(REF, PR, str(checkout))
    assert context.current_node == "self-review"
    assert context.status == "in-progress"
    assert _state(_spec(checkout)).current_node == "implementation"
