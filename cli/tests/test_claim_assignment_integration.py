"""A claim's answer says what comes next (issue-551, Requirement 1).

A session that claimed a node was answered ``advanced to <node>`` and nothing
else, so it ended its turn at a boundary it was meant to cross. These drive the
service's own entry point for a claim (``core.graphs.complete``) and a *real*
:class:`GraphLink` over the shipped loop in a checkout under ``tmp_path``.

Feature: A claim returns the next assignment
Requirement: docs/specs/issue-551/requirements.md
"""

from __future__ import annotations

import subprocess

import pytest

from the_loop import prompts
from the_loop.core import graphs as core_graphs
from the_loop.graph.state import WorkItemState
from the_loop.sessions import SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent

REF = WorkItemRef.parse("github:octo/repo#113")
ITEM = "issue-113"
REVIEWER = "octocat"


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


def _spec(checkout):
    return checkout / "docs" / "specs" / ITEM


def _stand_on(state_dir, node):
    state = WorkItemState.load(state_dir, ITEM)
    state.enter(node)
    state.save(state_dir)


def test_a_claim_returns_the_next_assignment_and_says_to_continue(checkout):
    """
    Feature: A claim returns the next assignment
    Scenario: a claim returns the next assignment and says to continue
      Given a work item whose pointer is on the agent-owned self-review node
      And its evidence record is committed, so the node's exit gate is met
      When the session claims the node complete
      Then the answer carries the critic-review node's assignment as its own field
      And the answer says the session continues with that node in the same turn

    Requirement: docs/specs/issue-551/requirements.md#R1.1
    Requirement: docs/specs/issue-551/requirements.md#R1.2
    """
    _stand_on(_spec(checkout), "self-review")
    evidence = _spec(checkout) / "evidence"
    evidence.mkdir()
    (evidence / "self-review.md").write_text("## Review cycles\n\none round\n")

    answer = core_graphs.complete(
        str(checkout), ITEM, node="self-review", actor="session", ref=REF.ref
    )

    assert answer["moved"] and answer["currentNode"] == "critic-review"
    assert answer["next"]["node"] == "critic-review"
    assert answer["next"]["actor"] == "agent"
    assert answer["next"]["continue"] is True
    assert "you are now at node: critic-review" in answer["assignment"]
    assert f"the-loop graph complete {ITEM}`" in answer["assignment"]
    assert prompts.load("assignment/continue", inline=True) in answer["assignment"]


def test_an_advance_the_daemon_drives_delivers_the_assignment_once(tmp_path, checkout):
    """
    Feature: A claim returns the next assignment
    Scenario: an advance the daemon drives delivers the assignment once
      Given a work item parked at the human-owned requirements-approval node
      And a daemon whose graph link can deliver into the work item's session
      When an authorized reviewer comments "approved"
      Then the design node's assignment is delivered into the session once
      And the advance is marked as one whose assignment was delivered
      And a claim the session replays for the node it left carries no assignment

    Requirement: docs/specs/issue-551/requirements.md#R1.5
    """
    delivered = []
    link = Dispatcher(
        registry=SessionRegistry(tmp_path / "sessions"),
        adapters={},
        config=RoutingConfig.from_mapping(
            {"authorizedUsers": [REVIEWER], "control": {"enabled": False}}, None
        ),
    ).graphlink
    link.assignment_sink = lambda work_item, pr, text: delivered.append(text) or True
    (_spec(checkout) / "requirements.md").write_text(
        "---\nstatus: approved\n---\n\n# R\n"
    )
    _stand_on(_spec(checkout), "requirements-approval")

    report = link.on_event(
        REF,
        str(checkout),
        RoutedEvent(
            event="issue_comment",
            action="created",
            delivery_id="d-1",
            work_items=[REF],
            payload={"comment": {"body": "approved", "user": {"login": REVIEWER}}},
        ),
    )

    entered = WorkItemState.load(_spec(checkout), ITEM).current_node
    assert entered == "design"
    assert len(delivered) == 1 and "you are now at node: design" in delivered[0]
    assert report is not None, "the graph ran"
    assert report.entered == "design" and report.assignment_delivered

    replay = core_graphs.complete(
        str(checkout), ITEM, node="requirements-approval", ref=REF.ref
    )

    assert replay["status"] == "noop"
    assert "assignment" not in replay and "next" not in replay
    assert len(delivered) == 1
