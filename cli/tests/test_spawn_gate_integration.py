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


# -- the released session carries what the operator declared (issue-377) ---------
#
# These compose the dispatcher the way the DAEMONS do — through
# `poller.daemon._build_dispatcher` — because a hand-built dispatcher is exactly how
# issue-377 stayed invisible to a green suite: the fixture above hands in an adapter
# with no arguments, so nothing here ever asked whether the daemon's own adapters
# carried the config.

REF_377 = "github:octo/repo#377"


class _GateLink(_Link):
    """A parked gate that an authorized reply answers — freezing ``model`` into the
    work item's own state file in the checkout, the way `phase-selection` does."""

    def __init__(self, freeze_model=""):
        super().__init__(parked=False)
        self.freeze_model = freeze_model

    def on_arm(self, work_item, cwd, routed=None):
        from the_loop.graph.state import WorkItemState

        self.armed.append((work_item.ref, routed))
        if self.freeze_model:
            spec = Path(cwd) / "docs" / "specs" / "issue-377"
            spec.mkdir(parents=True, exist_ok=True)
            state = WorkItemState(work_item=work_item.ref)
            state.model = self.freeze_model
            state.save(spec)
        return False


def _daemon_dispatcher(tmp_path, link, cli_config, events_path=None):
    """The poller's own composition, with the runner and the harness binary stubbed."""
    from the_loop import eventlog
    from the_loop.harness.base import TrustResult
    from the_loop.poller.daemon import _build_dispatcher
    from the_loop.state import layout_from_config

    checkout = tmp_path / "co"
    checkout.mkdir(exist_ok=True)
    routing = {
        "spawnOnUnmatched": "always",
        "authorizedUsers": ["octo"],
        "control": {"requireStartCommand": False},
        "registryDir": str(tmp_path / "local"),
        "spawnWorkdir": str(checkout),
        "reactions": {"enabled": False},
    }
    routing.update(cli_config.get("routing") or {})
    cli_config = dict(cli_config, routing=routing)
    cli_config.setdefault("state", {"root": str(tmp_path / "state")})
    dispatcher, _ = _build_dispatcher(
        routing, layout_from_config(cli_config), lambda: cli_config
    )
    tmux = FakeTmux()
    dispatcher.tmux = tmux
    for adapter in dispatcher.adapters.values():
        adapter.is_available = lambda: True  # type: ignore[method-assign]
        adapter.prepare_environment = (  # type: ignore[method-assign]
            lambda cwd, root=None: TrustResult()
        )
    dispatcher.graphlink = link
    if events_path is not None:
        eventlog.configure("poll", path=events_path, enabled=True)
    return dispatcher, tmux


def _release(number=377, delivery="d-377", body="the-loop execute"):
    payload = {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": number},
        "comment": {"body": body, "user": {"login": "octo"}},
    }
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id=delivery,
        work_items=extract_work_items("issue_comment", payload),
        payload=payload,
    )


def test_a_released_session_is_launched_with_every_configured_harness_argument(
    tmp_path,
):
    """Feature: a released work item is launched with the arguments the operator declared (issue-377)

    Scenario: a session released from the human-start gate is launched with every configured harness argument
      Given a CLI config that declares `--dangerously-skip-permissions` under `harnesses[].args` only
      And a dispatcher composed the way the poller daemon composes it
      When an authorized issue_comment releases a parked work item
      Then the session it spawns records every configured argument
      And the session.spawned event names that argv

    Requirement: docs/specs/issue-377/bugfix.md R1.1, R1.5, R4.1
    """
    from the_loop import eventlog

    log = tmp_path / "events.jsonl"
    dispatcher, tmux = _daemon_dispatcher(
        tmp_path,
        _GateLink(),
        {
            "harnesses": [
                {
                    "name": "claude",
                    "default": True,
                    "args": ["--dangerously-skip-permissions"],
                }
            ]
        },
        events_path=log,
    )
    try:
        dispatcher.handle(_release())
        assert _wait(lambda: tmux.spawns)
        dispatcher.stop()
        session = dispatcher.registry.find_by_work_item(REF_377)
        assert session is not None
        assert session.harness_args == ["--dangerously-skip-permissions"]
        (spawned,) = eventlog.read_events(log, types=["session.spawned"])
        assert spawned["gh_event"] == "issue_comment"
        assert spawned["harness_args"] == ["--dangerously-skip-permissions"]
    finally:
        eventlog.reset()


def test_the_deprecated_routing_harness_args_still_reach_a_released_session(
    tmp_path,
):
    """Feature: a released work item is launched with the arguments the operator declared (issue-377)

    Scenario: the deprecated routing.harnessArgs still reaches a released session
      Given a CLI config that declares the flag under `routing.harnessArgs.claude` only
      When an authorized issue_comment releases a parked work item
      Then the session it spawns records that argument

    Requirement: docs/specs/issue-377/bugfix.md R1.1
    """
    dispatcher, tmux = _daemon_dispatcher(
        tmp_path,
        _GateLink(),
        {"routing": {"harnessArgs": {"claude": ["--permission-mode", "acceptEdits"]}}},
    )
    dispatcher.handle(_release())
    assert _wait(lambda: tmux.spawns)
    dispatcher.stop()
    session = dispatcher.registry.find_by_work_item(REF_377)
    assert session is not None
    assert session.harness_args == ["--permission-mode", "acceptEdits"]


def test_the_session_spawned_by_the_gate_answering_reply_runs_on_the_model_it_froze(
    tmp_path,
):
    """Feature: a released work item is launched with the arguments the operator declared (issue-377)

    Scenario: the session spawned by the gate-answering reply already runs on the model it froze
      Given a CLI config that declares the flag under `harnesses[].args` and offers `opus-5`
      And a gate whose answer freezes `opus-5` into the work item's own state file
      When the reply that answers the gate arrives
      Then the session it spawns is launched with the flag followed by `--model opus-5`
      And its record carries the model
      And the next event is delivered into it rather than re-launching it

    Requirement: docs/specs/issue-377/bugfix.md R2.1, R2.2, R4.2
    """
    dispatcher, tmux = _daemon_dispatcher(
        tmp_path,
        _GateLink(freeze_model="opus-5"),
        {
            "harnesses": [
                {
                    "name": "claude",
                    "default": True,
                    "args": ["--dangerously-skip-permissions"],
                }
            ],
            "models": ["opus-5"],
        },
    )
    dispatcher.handle(_release())
    assert _wait(lambda: tmux.spawns)
    session = dispatcher.registry.find_by_work_item(REF_377)
    assert session is not None
    assert session.harness_args == [
        "--dangerously-skip-permissions",
        "--model",
        "opus-5",
    ]
    assert session.model == "opus-5"

    dispatcher.handle(_release(delivery="d-378", body="and one more thing"))
    assert _wait(lambda: tmux.delivers)
    dispatcher.stop()
    assert len(tmux.spawns) == 1, "a session on the right argv is delivered into"


def test_abuse_a_forged_model_in_the_state_file_buys_nothing_on_the_post_gate_spawn(
    tmp_path,
):
    """Feature: a released work item is launched with the arguments the operator declared (issue-377)

    Scenario: a forged model in the state file buys nothing on the post-gate spawn
      Given a gate whose answer writes an UNDECLARED model into the work item's state file
      When the reply that answers the gate spawns the session
      Then the argv carries the operator's arguments and nothing else
      And the record carries no model

    Requirement: docs/specs/issue-377/bugfix.md § Security considerations A1
    """
    dispatcher, tmux = _daemon_dispatcher(
        tmp_path,
        _GateLink(freeze_model="smuggled-9"),
        {
            "harnesses": [
                {
                    "name": "claude",
                    "default": True,
                    "args": ["--dangerously-skip-permissions"],
                }
            ],
            "models": ["opus-5"],
        },
    )
    dispatcher.handle(_release())
    assert _wait(lambda: tmux.spawns)
    dispatcher.stop()
    session = dispatcher.registry.find_by_work_item(REF_377)
    assert session is not None
    assert session.harness_args == ["--dangerously-skip-permissions"]
    assert session.model == ""
