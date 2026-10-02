"""Integration: closing a work item the instance accepted but never launched (issue-453).

A real :class:`Dispatcher` + :class:`SessionRegistry` + :class:`ControlStore`
on a tmp path, with the spawn seam on :class:`FakeTmux`. What is asserted is
what an operator gets after ``the-loop sessions start`` parked a work item at
its first human gate (a control record stamped with this instance, no session —
issue-358) and ``the-loop ticket close`` ran: the ticket is closed, the start is
cancelled, and the next event that would have spawned the item spawns nothing.
Beside it, the two things that must not change: a record this instance did not
write grants nothing, and a session-backed item closes as it did before, with
its local closure still the daemon's on the ``closed`` event.

Spec: docs/specs/issue-453/testing-plan.md T4.
"""

from __future__ import annotations

import time

import pytest

from conftest import FakeTmux, StubInteractiveAdapter
from ghfakes import FakeGitHubClient
from the_loop.control import ControlConfig, ControlStore
from the_loop.core import github_ops
from the_loop.instance import InstanceConfig
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.state import layout_from_config
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent, extract_work_items

LABEL = "the-loop: auto-execute"
REF = "github:octo/repo#15"
INSTANCE = "alpha"


def _wait(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


@pytest.fixture
def setup(tmp_path):
    """The daemon's dispatcher and the CLI's config over ONE state root, so the
    verb and the dispatcher read the same portable record."""
    config = {
        "state": {"root": str(tmp_path / ".the-loop")},
        "routing": {"registryDir": str(tmp_path / "local")},
        "instance": {"name": INSTANCE},
    }
    layout = layout_from_config(config)
    registry = SessionRegistry(tmp_path / "local")
    tmux = FakeTmux()
    routing = RoutingConfig(
        registry_dir=str(tmp_path / "local"),
        portable_dir=layout.portable_dir,
        spawn_on_unmatched="labeled",
        auto_execute_labels=[LABEL],
        spawn_workdir=str(tmp_path),
        control=ControlConfig(),  # defaults: enabled, requireStartCommand
        authorized_users=["octocat"],
        instance=InstanceConfig(name=INSTANCE),
    )
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=routing,
        tmux_runner=tmux,
    )
    store = ControlStore(layout.portable_dir)
    yield dispatcher, registry, tmux, store, config
    dispatcher.stop(timeout=5)


def labeled_event(delivery="l-1"):
    payload = {
        "action": "labeled",
        "label": {"name": LABEL},
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15, "labels": [{"name": LABEL}]},
        "sender": {"login": "octocat"},
    }
    return RoutedEvent(
        event="issues",
        action="labeled",
        delivery_id=delivery,
        work_items=extract_work_items("issues", payload),
        payload=payload,
        labeled=True,
    )


def control_start_event(delivery="cli-start-1"):
    """The event `sessions start` synthesises (core.sessions._spawn_for_start)."""
    payload = {
        "action": "control-start",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15},
    }
    return RoutedEvent(
        event="issues",
        action="control-start",
        delivery_id=delivery,
        work_items=[WorkItemRef.parse(REF)],
        payload=payload,
        labeled=True,
    )


def close_event(delivery="c-1"):
    payload = {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15, "labels": [], "state_reason": "completed"},
        "sender": {"login": "octocat"},
    }
    return RoutedEvent(
        event="issues",
        action="closed",
        delivery_id=delivery,
        work_items=extract_work_items("issues", payload),
        payload=payload,
    )


def park(store, instance=INSTANCE):
    """What `sessions start` leaves behind when the daemon parks the item at its
    first human gate: the arming, stamped with the instance, and no session."""
    store.record(REF, "start", source="cli", actor="operator", instance=instance)
    assert store.start_requested(REF)


def register(registry):
    return registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-0",
            cwd=".",
            tmux_target="loop-github-octo-repo-15",
        ),
        force=True,
    )


def test_a_parked_work_item_is_closed_and_cannot_launch_later(setup):
    """
    Feature: lifecycle operations on a work item parked before harness launch
      Scenario: the operator closes a parked item through the-loop
        Given a work item this instance armed and parked at its first human gate
        And no harness session exists for it
        When the operator runs `the-loop ticket close` for it
        Then the ticket is closed on GitHub
        And the pending start is cancelled
        And a later labelled event or control-start spawns no session
    Requirement: docs/specs/issue-453/requirements.md R1.1, R2.1, R2.2, R2.5, abuse 4
    """
    dispatcher, registry, tmux, store, config = setup
    park(store)
    fake = FakeGitHubClient()

    result = github_ops.close_ticket(REF, "not_planned", config=config, client=fake)

    assert result["exitCode"] == 0 and result["startCancelled"] is True
    assert fake.closed == [("octo", "repo", 15, "not_planned")]
    assert registry.find_by_work_item(REF) is None, "no session was invented"
    assert store.start_requested(REF) is False

    dispatcher.handle(labeled_event())
    dispatcher.handle(control_start_event())
    assert _wait(lambda: True, 0.2)
    assert tmux.spawns == [] and registry.find_by_work_item(REF) is None


def test_abuse_453_a1_a_record_this_instance_did_not_write_is_refused(setup):
    """
    Feature: lifecycle operations on a work item parked before harness launch
      Scenario: an arbitrary portable record grants no authority
        Given a control record for the work item stamped by another instance
        When the operator runs `the-loop ticket close` for it on this instance
        Then the close is refused and nothing is sent to GitHub
        And the other instance's arming stands, so the dispatcher is unchanged
    Requirement: docs/specs/issue-453/requirements.md R3.1, R3.2, abuse 1
    """
    dispatcher, registry, tmux, store, config = setup
    park(store, instance="beta")
    fake = FakeGitHubClient()

    result = github_ops.close_ticket(REF, config=config, client=fake)
    assert result["exitCode"] == 1 and fake.closed == []
    assert "not a work item registered on this instance" in " ".join(
        m["text"] for m in result["messages"]
    )
    assert store.start_requested(REF)

    unrelated = github_ops.close_ticket(
        "github:octo/repo#99", config=config, client=fake
    )
    assert unrelated["exitCode"] == 1 and fake.closed == []


def test_a_session_backed_work_item_closes_as_before(setup):
    """
    Feature: lifecycle operations on a work item parked before harness launch
      Scenario: a session-backed close is unchanged
        Given a work item with a live session on this instance
        When the operator runs `the-loop ticket close` for it
        Then the ticket is closed and no stop is recorded
        And the daemon's closed event ends the session and forgets the arming
    Requirement: docs/specs/issue-453/requirements.md R2.6
    """
    dispatcher, registry, tmux, store, config = setup
    park(store)
    register(registry)
    fake = FakeGitHubClient()

    result = github_ops.close_ticket(REF, config=config, client=fake)
    assert result["exitCode"] == 0 and result["startCancelled"] is False
    assert fake.closed == [("octo", "repo", 15, "completed")]
    record = store.get(REF)
    assert record is not None and record.command == "start"

    dispatcher.handle(close_event())
    # The daemon's own closure: the session is ended (and its record released by
    # the issue-closed cleanup), the arming forgotten, the item stamped ended.
    assert registry.find_by_work_item(REF) is None
    assert store.get(REF) is None and store.ended(REF) is not None
