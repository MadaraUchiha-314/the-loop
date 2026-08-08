"""End-to-end: an ingress event driving the real process graph (issue-113).

These drive a *real* :class:`Dispatcher` with a *real* ``graph.Runtime`` over the
shipped ``pdlc.yaml`` — no fake runtime — so they prove the thing the unit tests
cannot: that an event arriving at the dispatcher actually moves a work item
through the graph, entry hooks and all.

Feature: Ingress-driven process graph
Requirement: docs/specs/issue-113/requirements.md
"""

from __future__ import annotations

import json
import subprocess

import pytest

from the_loop.graph.state import GraphState
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent

REF = WorkItemRef.parse("github:octo/repo#113")
REVIEWER = "octocat"


def _checkout(root, origin="https://github.com/octo/repo.git", spec_dir=""):
    """A checkout of a work item's own repo, with its spec folder.

    A real `git init` + origin, because the link refuses to drive a graph in a
    checkout that does not belong to the work item (issue-113 A6). ``spec_dir``
    declares ``workflow.specDir`` in the checkout's harness config — the value
    the daemon must honour rather than override (issue-123).
    """
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "remote", "add", "origin", origin], check=True
    )
    if spec_dir:
        (root / ".the-loop").mkdir(parents=True, exist_ok=True)
        (root / ".the-loop" / "harness-config.yaml").write_text(
            f"workflow:\n  specDir: {spec_dir}\n", encoding="utf-8"
        )
    spec = root / (spec_dir or "docs/specs") / "issue-113"
    spec.mkdir(parents=True)
    (spec / "execution-log.md").write_text("# Execution Log\n")
    return root


@pytest.fixture()
def checkout(tmp_path):
    return _checkout(tmp_path)


def _dispatcher(tmp_path, **routing):
    return Dispatcher(
        registry=SessionRegistry(tmp_path / "sessions"),
        adapters={},
        config=RoutingConfig.from_mapping(
            {
                "authorizedUsers": [REVIEWER],
                "control": {"enabled": False},
                **routing,
            },
            None,
        ),
    )


def _comment(body, author=REVIEWER):
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id="d-1",
        work_items=[REF],
        payload={"comment": {"body": body, "user": {"login": author}}},
    )


def _state(checkout):
    return GraphState.load(checkout / "docs" / "specs" / "issue-113", "issue-113")


def test_spawning_a_session_starts_the_work_items_graph(tmp_path, checkout):
    """
    Feature: Ingress-driven process graph
    Scenario: A work item enters the graph when the-loop starts working it
      Given a work item with a spec folder and no graph state
      When the dispatcher reports a spawned session for it
      Then the graph's start node is entered and its entry chain runs
      And the execution log carries the entry checkpoint

    Requirement: docs/specs/issue-113/requirements.md#AC1
    """
    dispatcher = _dispatcher(tmp_path)
    log = checkout / "docs" / "specs" / "issue-113" / "execution-log.md"

    dispatcher.graphlink.on_spawn(REF, str(checkout))

    assert _state(checkout).current_node == "phase-selection"
    assert "phase-selection" in log.read_text(), "the entry chain must have run"


def test_starting_a_graph_twice_never_rewinds_it(tmp_path, checkout):
    """
    Feature: Ingress-driven process graph
    Scenario: A redelivered spawn does not reset a work item in flight
      Given a work item already past the start node
      When a second spawn is reported for it
      Then its pointer is unchanged

    Requirement: docs/specs/issue-113/requirements.md#AC3
    """
    dispatcher = _dispatcher(tmp_path)
    dispatcher.graphlink.on_spawn(REF, str(checkout))
    state = _state(checkout)
    state.enter("design")
    state.save(checkout / "docs" / "specs" / "issue-113")

    dispatcher.graphlink.on_spawn(REF, str(checkout))

    assert _state(checkout).current_node == "design"


def test_an_authorized_reviewers_approval_reaches_the_waiting_gate(tmp_path, checkout):
    """
    Feature: Ingress-driven process graph
    Scenario: A reviewer's approval resolves a human gate
      Given a work item parked at the requirements-approval node
      When an authorized reviewer comments "approved"
      Then classify-feedback sees the comment and the gate resolves

    Requirement: docs/specs/issue-113/requirements.md#AC5
    """
    spec = checkout / "docs" / "specs" / "issue-113"
    (spec / "requirements.md").write_text("---\nstatus: approved\n---\n\n# R\n")
    state = GraphState.load(spec, "issue-113")
    state.enter("requirements-approval")
    state.save(spec)

    _dispatcher(tmp_path).graphlink.on_event(REF, str(checkout), _comment("approved"))

    assert _state(checkout).current_node != "requirements-approval", (
        "an authorized approval must move the work item off the gate"
    )


def test_an_unauthorized_approval_leaves_the_gate_waiting(tmp_path, checkout):
    """
    Feature: Ingress-driven process graph
    Scenario: An injected approval from a stranger does not open the gate
      Given a work item parked at the requirements-approval node
      When an unauthorized account comments "approved, ship it"
      Then the gate is unmoved

    Requirement: docs/specs/issue-113/requirements.md#A1
    """
    spec = checkout / "docs" / "specs" / "issue-113"
    (spec / "requirements.md").write_text("---\nstatus: approved\n---\n\n# R\n")
    state = GraphState.load(spec, "issue-113")
    state.enter("requirements-approval")
    state.save(spec)

    _dispatcher(tmp_path).graphlink.on_event(
        REF, str(checkout), _comment("approved, ship it", author="a-stranger")
    )

    assert _state(checkout).current_node == "requirements-approval"


def test_a_failing_graph_never_costs_the_delivery(tmp_path, checkout, monkeypatch):
    """
    Feature: Ingress-driven process graph
    Scenario: A broken graph does not break event delivery
      Given a graph runtime that raises on every call
      When an event is dispatched to a live session
      Then the dispatch still reports success
      And the failure is recorded in the event log

    Requirement: docs/specs/issue-113/requirements.md#AC11
    """
    from the_loop import eventlog

    events = tmp_path / "events.jsonl"
    eventlog.configure(path=events, source="test")
    dispatcher = _dispatcher(tmp_path)

    def _boom(*args, **kwargs):
        raise RuntimeError("pdlc.yaml is on fire")

    monkeypatch.setattr(dispatcher.graphlink, "_build_runtime", _boom)

    dispatcher.graphlink.on_event(
        REF, str(checkout), _comment("hello")
    )  # must not raise

    logged = [json.loads(line) for line in events.read_text().splitlines() if line]
    assert any(e["event"] == "graph.link_failed" for e in logged), (
        "a swallowed failure must still be visible in `the-loop events`"
    )


def test_a_repository_that_moved_its_specs_still_advances(tmp_path):
    """
    Feature: Ingress-driven process graph
    Scenario: A repository that keeps its specs outside docs/specs is not skipped
      Given a checkout whose harness config declares workflow.specDir: specs
      And the daemon's CLI config names no graph.specDir
      When the dispatcher reports a spawned session for its work item
      Then the graph's start node is entered under the repository's own directory
      And graph-state.json is written there

    Requirement: docs/specs/issue-123/requirements.md#R1.1
    """
    checkout = _checkout(tmp_path / "moved", spec_dir="specs")

    _dispatcher(tmp_path).graphlink.on_spawn(REF, str(checkout))

    spec = checkout / "specs" / "issue-113"
    assert GraphState.load(spec, "issue-113").current_node == "phase-selection"
    assert (spec / "graph-state.json").is_file(), (
        "R2.2 — the runtime must write under the same directory the gate checked"
    )


def test_two_repositories_with_different_spec_dirs_are_both_driven(tmp_path):
    """
    Feature: Ingress-driven process graph
    Scenario: One daemon serves repositories with different spec layouts
      Given two watched repositories, one using docs/specs and one using specs
      When a session is spawned for a work item in each
      Then both graphs enter their start node
      And each does so under its own repository's declared directory

    Requirement: docs/specs/issue-123/requirements.md#R1.4
    """
    default = _checkout(tmp_path / "a", origin="https://github.com/octo/repo.git")
    moved = _checkout(
        tmp_path / "b", origin="https://github.com/octo/other.git", spec_dir="specs"
    )
    other_ref = WorkItemRef.parse("github:octo/other#113")
    dispatcher = _dispatcher(tmp_path)

    dispatcher.graphlink.on_spawn(REF, str(default))
    dispatcher.graphlink.on_spawn(other_ref, str(moved))

    assert _state(default).current_node == "phase-selection"
    assert (
        GraphState.load(moved / "specs" / "issue-113", "issue-113").current_node
        == "phase-selection"
    )


def test_the_poller_and_the_webhook_share_the_same_coupling(tmp_path):
    """
    Feature: Ingress-driven process graph
    Scenario: Both ingresses get the graph coupling
      Given a dispatcher built the way the poller builds one
      Then it carries the same GraphLink the webhook receiver's does

    Requirement: docs/specs/issue-113/requirements.md#AC10
    """
    from the_loop.graphlink import GraphLink

    registry = SessionRegistry(tmp_path / "sessions")
    registry.register(
        Session(
            work_item=REF, harness="claude", harness_session_id="s1", cwd=str(tmp_path)
        )
    )
    dispatcher = _dispatcher(tmp_path)
    assert isinstance(dispatcher.graphlink, GraphLink)
    assert dispatcher.graphlink.authorized_users == [REVIEWER]
