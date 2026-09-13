"""The session is spawned AFTER the gate is answered, not before (issue-358, R8).

Feature: a work item gets its harness session only once somebody has said what it
should do — so the first session already runs on the model the gate froze, and an
unanswered gate costs no tmux session and no harness process.
"""

from __future__ import annotations

import time
from pathlib import Path

from conftest import FakeTmux, StubInteractiveAdapter
from the_loop.control import ControlConfig
from the_loop.sessions import SessionRegistry, Session, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent, extract_work_items

REF = "github:octo/repo#15"


class _Link:
    """A graph link whose parked-ness the test decides."""

    def __init__(self, parked=False):
        self.parked = parked
        self.armed = []
        self.spawned = []

    def adopt(self, work_item, cwd):
        pass

    def on_arm(self, work_item, cwd, routed=None):
        self.armed.append((work_item.ref, routed))
        return self.parked

    def context(self, work_item, cwd):
        return None

    def on_event(self, work_item, cwd, routed):
        return None

    def on_spawn(self, work_item, cwd, session_id="", runner="", routed=None):
        self.spawned.append(work_item.ref)

    def on_close(self, work_item, cwd):
        pass

    def on_cleanup(self, work_item, cwd, reason=""):
        pass


def _dispatcher(tmp_path, link, **overrides):
    registry = SessionRegistry(tmp_path / "sessions")
    overrides.setdefault("control", ControlConfig(require_start_command=False))
    overrides.setdefault("spawn_on_unmatched", "always")
    tmux = FakeTmux()
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=RoutingConfig(**overrides),
        tmux_runner=tmux,
    )
    dispatcher.graphlink = link
    return registry, dispatcher, tmux


def _comment(delivery="d-1", body="looks good"):
    payload = {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15},
        "comment": {"body": body, "user": {"login": "octo"}},
    }
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id=delivery,
        work_items=extract_work_items("issue_comment", payload),
        payload=payload,
    )


def _wait(predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_an_armed_work_item_gets_no_session_until_its_gate_is_answered(tmp_path):
    """Feature: spawning after the gate (issue-358, R8)

    Scenario: an armed work item gets no session until its gate is answered
      Given a work item whose graph pointer parks on a human start gate
      When an event arms it
      Then the graph is entered and the gate's own hooks post their checklist
      And no tmux session is created
      And no session is registered for the work item

    Requirement: docs/specs/issue-358/requirements.md R8.1, R8.8
    """
    link = _Link(parked=True)
    registry, dispatcher, tmux = _dispatcher(tmp_path, link)
    dispatcher.handle(_comment())
    assert _wait(lambda: link.armed)
    dispatcher.stop()

    assert link.armed, "the graph must still be entered when the spawn is deferred"
    assert tmux.spawns == [], "a parked gate must not cost a tmux session"
    assert link.spawned == [], "on_spawn is for a session that exists"
    assert registry.find_by_work_item(REF) is None


def test_the_arming_event_still_reaches_the_first_gate(tmp_path):
    """Feature: spawning after the gate (issue-358, R8)

    Scenario: the arming comment is handed to the gate it lands on
      Given a work item whose graph pointer parks on a human start gate
      When the event that arms it arrives
      Then that event is handed to the graph with the arm, so a gate it answers
        is answered by it
      And issue-199's hand-off is unchanged, only earlier

    Requirement: docs/specs/issue-358/requirements.md R8.5
    """
    link = _Link(parked=True)
    registry, dispatcher, tmux = _dispatcher(tmp_path, link)
    dispatcher.handle(_comment(body="please have a look"))
    assert _wait(lambda: link.armed)
    dispatcher.stop()

    _, routed = link.armed[0]
    assert routed is not None
    assert "please have a look" in routed.payload["comment"]["body"]


def test_an_unparked_work_item_spawns_exactly_as_before(tmp_path):
    """Feature: spawning after the gate (issue-358, R8)

    Scenario: nothing is deferred when the pointer is not parked at a gate
      Given a work item whose graph reports no parked human start gate
      When an event arms it
      Then a tmux session is spawned
      And the graph records the session binding

    Requirement: docs/specs/issue-358/requirements.md R8.3, R8.6
    """
    link = _Link(parked=False)
    registry, dispatcher, tmux = _dispatcher(tmp_path, link)
    dispatcher.handle(_comment())
    assert _wait(lambda: tmux.spawns)
    dispatcher.stop()

    assert tmux.spawns, "an unparked item must spawn exactly as it does today"
    assert link.spawned == [REF]
    assert registry.find_by_work_item(REF) is not None


def test_a_mid_graph_work_item_still_respawns(tmp_path):
    """Feature: spawning after the gate (issue-358, R8)

    Scenario: a mid-graph work item still respawns
      Given a registered session whose tmux session has died
      And a graph link that would park a FRESH item at its gate
      When an event arrives for that work item
      Then the session is respawned rather than deferred
      And the deferral rule cannot strand a work item that is already working

    Requirement: docs/specs/issue-358/requirements.md R8.3
    """
    link = _Link(parked=True)
    registry, dispatcher, tmux = _dispatcher(tmp_path, link)
    tmux.session_missing = True  # the tmux session died under a live registration
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(Path(tmp_path).resolve()),
            tmux_target="loop-octo-repo-15",
        )
    )
    dispatcher.handle(_comment(delivery="d-2"))
    assert _wait(lambda: tmux.spawns)
    dispatcher.stop()

    # The respawn path never consults on_arm: deferral is only ever about a work
    # item that has not started, so nothing already under way can be withheld.
    assert tmux.spawns, "a dead session must be respawned, parked gate or not"
    assert link.armed == []
