"""Integration tests for instance scope end to end (issue-322).

Two real :class:`Dispatcher` instances — each with its own registry, portable
state and ``FakeTmux`` — fed the **same** event objects, the way two daemons on
two machines would each receive one GitHub delivery. What is asserted is what an
operator gets: which instance spawns, which records, which stays silent, and
what the event log says about the one that stayed silent.

Spec: docs/specs/issue-322/requirements.md R2, R3, R4.1.
"""

from __future__ import annotations

import time

import pytest

from conftest import FakeTmux, StubInteractiveAdapter
from the_loop import eventlog
from the_loop.control import ControlConfig, ControlStore
from the_loop.core import sessions as core_sessions
from the_loop.instance import (
    ADDRESSED,
    ADDRESSED_ELSEWHERE,
    AMBIGUOUS_ADDRESS,
    INSTANCE_LOCKED,
    LOCKED,
    OPEN,
    UNADDRESSED,
    InstanceConfig,
)
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent, extract_work_items

LABEL = "the-loop: auto-execute"
REF = "github:octo/repo#15"
START = "the-loop start"


def _wait(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class _Instance:
    """One the-loop instance: a dispatcher over its own state root."""

    def __init__(self, root, name="", mode=OPEN, declared=()):
        self.root = root
        self.registry = SessionRegistry(root / "local")
        self.tmux = FakeTmux()
        self.config = RoutingConfig(
            registry_dir=str(root / "local"),
            portable_dir=str(root / "portable"),
            spawn_on_unmatched="labeled",
            auto_execute_label=LABEL,
            spawn_workdir=str(root),
            control=ControlConfig(),
            authorized_users=["octocat"],
            instance=InstanceConfig(name=name, mode=mode, declared=tuple(declared)),
        )
        self.dispatcher = Dispatcher(
            registry=self.registry,
            adapters={"claude": StubInteractiveAdapter()},
            config=self.config,
            tmux_runner=self.tmux,
        )
        self.store = ControlStore(root / "portable")

    def stop(self):
        self.dispatcher.stop(timeout=5)

    def spawned(self):
        return self.registry.find_by_work_item(REF) is not None


@pytest.fixture
def instances(tmp_path):
    made = []

    def make(name="", mode=OPEN, declared=()):
        instance = _Instance(tmp_path / (name or "unnamed"), name, mode, declared)
        made.append(instance)
        return instance

    yield make
    for instance in made:
        instance.stop()


@pytest.fixture
def events(monkeypatch):
    """Every event-log record emitted during the test, in order."""
    records = []

    class _Log:
        enabled = True

        def emit(self, event, level="info", **fields):
            records.append({"event": event, "level": level, **fields})

    monkeypatch.setattr(eventlog, "_log", _Log())
    return records


def comment_event(body, delivery="d-1", author="octocat", number=15):
    payload = {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": number, "labels": [{"name": LABEL}]},
        "comment": {
            "id": 1,
            "body": body,
            "html_url": "https://c/1",
            "user": {"login": author},
        },
        "sender": {"login": author},
    }
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id=delivery,
        work_items=extract_work_items("issue_comment", payload),
        payload=payload,
        labeled=False,
    )


def dropped(events, reason):
    return [
        e
        for e in events
        if e["event"] == "dispatch.dropped" and e.get("reason") == reason
    ]


def rejected(events, reason):
    return [
        e
        for e in events
        if e["event"] == "control.rejected" and e.get("reason") == reason
    ]


def register(instance, status="active"):
    return instance.registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-0",
            cwd=".",
            status=status,
            tmux_target="loop-github-octo-repo-15",
        ),
        force=True,
    )


# -- addressing --------------------------------------------------------------------


def test_an_addressed_start_reaches_only_the_instance_it_names(instances, events):
    """
    Feature: instances scoped to their own work items
      Scenario: An addressed start reaches only the instance it names
        Given two addressed instances, alpha and beta, watching one repository
        When an authorized user comments "the-loop start instance:alpha"
        Then alpha spawns a session and records the start as its own
        And beta spawns nothing, records nothing, and files a control.rejected
             naming the reason addressed-elsewhere
    Requirement: docs/specs/issue-322/requirements.md R2.3, R3.1, R3.2, R4.1
    """
    alpha = instances("alpha", ADDRESSED)
    beta = instances("beta", ADDRESSED)
    event = comment_event(f"{START} instance:alpha")

    alpha.dispatcher.handle(event)
    beta.dispatcher.handle(event)

    assert _wait(alpha.spawned)
    assert alpha.store.get(REF).instance == "alpha"  # type: ignore[union-attr]
    assert _wait(lambda: True, 0.2)
    assert not beta.spawned() and beta.tmux.spawns == []
    assert beta.store.get(REF) is None
    refusals = rejected(events, ADDRESSED_ELSEWHERE)
    assert len(refusals) == 1 and refusals[0]["command"] == "start"
    assert beta.dispatcher.delivery_outcome("d-1") == "control-rejected"


def test_an_unaddressed_start_reaches_no_addressed_instance(instances, events):
    """
    Feature: instances scoped to their own work items
      Scenario: An unaddressed start on two addressed instances reaches neither
        Given two addressed instances watching one repository
        When an authorized user comments "the-loop start" with no address
        Then neither spawns, neither records, and each files a control.rejected
             naming the reason unaddressed
        And the delivery is settled on both, so it is not retried
    Requirement: docs/specs/issue-322/requirements.md R2.3, R2.5, R2.6
    """
    alpha = instances("alpha", ADDRESSED)
    beta = instances("beta", ADDRESSED)
    event = comment_event(START)

    alpha.dispatcher.handle(event)
    beta.dispatcher.handle(event)

    assert _wait(lambda: True, 0.2)
    assert not alpha.spawned() and not beta.spawned()
    assert alpha.store.get(REF) is None and beta.store.get(REF) is None
    assert len(rejected(events, UNADDRESSED)) == 2
    assert alpha.dispatcher.delivery_outcome("d-1") == "control-rejected"
    assert beta.dispatcher.delivery_outcome("d-1") == "control-rejected"


def test_an_open_unnamed_instance_behaves_as_before(instances, events):
    """
    Feature: instances scoped to their own work items
      Scenario: An open, unnamed instance is 13.3.1
        Given an instance with no instance block
        When an authorized user comments "the-loop start"
        Then it spawns exactly as before, with an unnamed control record
        And no scope refusal is recorded
    Requirement: docs/specs/issue-322/requirements.md R1.2, R2.2
    """
    plain = instances()
    plain.dispatcher.handle(comment_event(START))
    assert _wait(plain.spawned)
    assert plain.store.get(REF).instance == ""  # type: ignore[union-attr]
    assert not [e for e in events if e["event"] in ("control.rejected",)]


def test_an_address_to_another_instance_is_authoritative_even_when_managed(
    instances, events
):
    """
    Feature: instances scoped to their own work items
      Scenario: An explicit address wins over the managed set
        Given an open instance alpha with a live session for the work item
        When an authorized user comments "the-loop stop instance:beta"
        Then alpha does not stop its session and records nothing
        And it files a control.rejected naming addressed-elsewhere
    Requirement: docs/specs/issue-322/requirements.md R3.2
    """
    alpha = instances("alpha", OPEN)
    register(alpha)
    alpha.dispatcher.handle(comment_event("the-loop stop instance:beta"))
    assert _wait(lambda: True, 0.2)
    session = alpha.registry.find_by_work_item(REF)
    assert session is not None and session.status == "active"
    assert alpha.store.get(REF) is None
    assert len(rejected(events, ADDRESSED_ELSEWHERE)) == 1


def test_two_different_addresses_refuse_the_comment_everywhere(instances, events):
    """
    Feature: instances scoped to their own work items
      Scenario: A comment naming two instances is ambiguous
        Given an open instance alpha
        When an authorized user comments "the-loop start instance:alpha instance:beta"
        Then alpha spawns nothing and files ambiguous-address
    Requirement: docs/specs/issue-322/requirements.md R3.3
    """
    alpha = instances("alpha", OPEN)
    alpha.dispatcher.handle(comment_event(f"{START} instance:alpha instance:beta"))
    assert _wait(lambda: True, 0.2)
    assert not alpha.spawned()
    assert len(rejected(events, AMBIGUOUS_ADDRESS)) == 1


# -- locked --------------------------------------------------------------------------


def test_an_address_does_not_unlock_a_locked_instance_but_a_declaration_does(
    instances, events
):
    """
    Feature: instances scoped to their own work items
      Scenario: A locked instance takes only what its config declares
        Given a locked instance alpha declaring nothing
        When an authorized user comments "the-loop start instance:alpha"
        Then alpha spawns nothing and files instance-locked
        Given a locked instance gamma declaring the work item
        When the same unaddressed start reaches gamma
        Then gamma spawns
    Requirement: docs/specs/issue-322/requirements.md R2.4, abuse case 3
    """
    alpha = instances("alpha", LOCKED)
    alpha.dispatcher.handle(comment_event(f"{START} instance:alpha"))
    assert _wait(lambda: True, 0.2)
    assert not alpha.spawned() and alpha.store.get(REF) is None
    assert len(rejected(events, INSTANCE_LOCKED)) == 1

    gamma = instances("gamma", LOCKED, declared=[REF])
    gamma.dispatcher.handle(comment_event(START, delivery="d-2"))
    assert _wait(gamma.spawned)
    assert gamma.store.get(REF).instance == "gamma"  # type: ignore[union-attr]


# -- managed items ---------------------------------------------------------------------


@pytest.mark.parametrize("mode", [OPEN, ADDRESSED, LOCKED])
def test_a_managed_work_items_events_are_delivered_in_every_mode(
    instances, events, mode
):
    """
    Feature: instances scoped to their own work items
      Scenario: A managed work item is in scope whatever the mode
        Given an instance in <mode> with a live session for the work item
        When an authorized user comments on it without an address
        Then the comment is delivered into the session
        And no scope refusal is recorded
    Requirement: docs/specs/issue-322/requirements.md R2.1
    """
    alpha = instances("alpha", mode)
    register(alpha)
    alpha.dispatcher.handle(comment_event("please also update the README"))
    assert _wait(lambda: len(alpha.tmux.delivers) == 1)
    assert not [
        e for e in events if e["event"] in ("dispatch.dropped", "control.rejected")
    ]


def test_a_control_record_makes_a_work_item_managed(instances, events):
    """
    Feature: instances scoped to their own work items
      Scenario: A stopped work item is still this instance's
        Given an addressed instance holding a stop record for the work item
        When an authorized user comments "the-loop start" with no address
        Then the instance takes it — the record made the item its own
    Requirement: docs/specs/issue-322/requirements.md R2 (the managed set)
    """
    alpha = instances("alpha", ADDRESSED)
    alpha.store.record(REF, "stop", source="cli", instance="alpha")
    alpha.dispatcher.handle(comment_event(START))
    assert _wait(alpha.spawned)


# -- silence ---------------------------------------------------------------------------


def test_a_refused_event_leaves_no_mark(instances, events):
    """
    Feature: instances scoped to their own work items
      Scenario: A non-owner leaves nothing behind
        Given an addressed instance beta and a plain comment on an unmanaged item
        When the comment reaches beta
        Then beta files one dispatch.dropped naming unaddressed and its instance
        And writes no session record, no control record and no portable file
        And delivers nothing and spawns nothing
    Requirement: docs/specs/issue-322/requirements.md R2.6, abuse case 5
    """
    beta = instances("beta", ADDRESSED)
    beta.dispatcher.handle(comment_event("what is the status here?"))
    assert _wait(lambda: True, 0.2)
    drops = dropped(events, UNADDRESSED)
    assert len(drops) == 1
    assert drops[0]["instance"] == "beta" and drops[0]["work_items"] == [REF]
    assert not (beta.root / "portable").exists()
    assert beta.registry.list_sessions() == []
    assert beta.tmux.spawns == [] and beta.tmux.delivers == []
    assert beta.dispatcher.delivery_outcome("d-1") == UNADDRESSED


def test_an_unauthorized_address_grants_nothing(instances, events):
    """
    Feature: instances scoped to their own work items
      Scenario: An unauthorized commenter cannot steer with an address
        Given an addressed instance alpha
        When a non-authorized user comments "the-loop start instance:alpha"
        Then alpha spawns nothing and records nothing
        And the refusal is the authorized-actor guard's, not a scope acceptance
    Requirement: docs/specs/issue-322/requirements.md abuse case 1
    """
    alpha = instances("alpha", ADDRESSED)
    alpha.dispatcher.handle(comment_event(f"{START} instance:alpha", author="mallory"))
    assert _wait(lambda: True, 0.2)
    assert not alpha.spawned() and alpha.store.get(REF) is None
    assert len(rejected(events, "unauthorized-actor")) == 1


# -- the CLI path (R2.7) ----------------------------------------------------------------


def _cli_config(root, name, mode, declared=()):
    return {
        "state": {"root": str(root)},
        "instance": {
            "name": name,
            "scope": {"mode": mode, "workItems": list(declared)},
        },
        "routing": {
            "enabled": True,
            "spawnOnUnmatched": "labeled",
            "authorizedUsers": ["octocat"],
            "spawnWorkdir": str(root),
        },
    }


def test_sessions_start_on_a_locked_instance_is_refused_and_posts_nothing(
    tmp_path, events, monkeypatch
):
    """
    Feature: instances scoped to their own work items
      Scenario: `the-loop sessions start` on a locked instance
        Given a locked instance that does not manage the work item
        When the operator runs `the-loop sessions start <ref>` on it
        Then the start is refused with exit code 1 and effect instance-locked
        And nothing is recorded and no comment is posted
    Requirement: docs/specs/issue-322/requirements.md R2.7
    """
    posted = []
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment",
        lambda *a, **k: posted.append(a) or (True, ""),
    )
    config = _cli_config(tmp_path, "alpha", LOCKED)
    result = core_sessions.control_session(REF, "start", config=config)
    assert result["exitCode"] == 1 and result["effect"] == INSTANCE_LOCKED
    assert "locked" in result["output"]
    assert ControlStore(tmp_path / "portable").get(REF) is None
    assert posted == []
    assert len(rejected(events, INSTANCE_LOCKED)) == 1


def test_sessions_start_on_an_addressed_instance_claims_and_names_itself(
    tmp_path, events, monkeypatch
):
    """
    Feature: instances scoped to their own work items
      Scenario: `the-loop sessions start` on an addressed instance
        Given an addressed instance alpha and a spawn that succeeds
        When the operator runs `the-loop sessions start <ref>` on it
        Then the work item is claimed with the record naming alpha
        And the keyword posted back to the ticket carries "instance:alpha"
    Requirement: docs/specs/issue-322/requirements.md R2.7, R4.2
    """
    posted = []
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment",
        lambda item, body, **k: posted.append(body) or (True, ""),
    )
    config = _cli_config(tmp_path, "alpha", ADDRESSED)
    from the_loop.cli_config import apply_instance

    apply_instance(config)

    def fake_dispatcher(cfg, registry_dir, portable_dir):
        # The daemon's construction, minus the poller module: the same routing
        # mapping, the same layout, the control store `control_session` records
        # into (the real `_dispatcher_for` points the dispatcher at it too).
        routing = RoutingConfig.from_mapping(dict(cfg["routing"]))
        routing.registry_dir = registry_dir
        routing.spawn_workdir = str(tmp_path)
        dispatcher = Dispatcher(
            registry=SessionRegistry(registry_dir),
            adapters={"claude": StubInteractiveAdapter()},
            config=routing,
            tmux_runner=FakeTmux(),
        )
        dispatcher.control_store = core_sessions._control_store(cfg, portable_dir)
        return dispatcher, routing

    monkeypatch.setattr(core_sessions, "_dispatcher_for", fake_dispatcher)
    result = core_sessions.control_session(REF, "start", config=config)
    assert result["exitCode"] == 0, result["output"]
    record = ControlStore(tmp_path / "portable").get(REF)
    assert record is not None and record.instance == "alpha"
    assert posted and posted[0].splitlines()[0] == "the-loop start instance:alpha"
