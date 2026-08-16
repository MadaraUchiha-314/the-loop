"""Integration tests for execution control end to end (issue-106).

A real :class:`Dispatcher` + :class:`SessionRegistry` + :class:`ControlStore` on
a tmp path, driven by the ``RoutedEvent`` shape both ingress paths produce — so
these assert the behaviour an operator actually gets: a labelled work item that
waits to be started, a pause that holds events, a resume that lets them through
again, a stop that ends the session, and the poller declining to arm a spawn
nobody asked for.

Spec: docs/specs/issue-106/requirements.md.
"""

import time

import pytest

from conftest import FakeTmux, StubInteractiveAdapter
from the_loop.control import ControlConfig, ControlStore
from the_loop.poller import PollConfig, Poller, PollState
from the_loop.poller.base import Comment, PollProvider, WorkItem
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.workitem import WorkItemStore
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent, extract_work_items

LABEL = "the-loop: auto-execute"
REF = "github:octo/repo#15"
START_KEYWORD = "the-loop start"
STOP_KEYWORD = "the-loop stop"
PAUSE_KEYWORD = "the-loop pause"
RESUME_KEYWORD = "the-loop resume"


def _dispatcher(registry, tmux, config):
    """A dispatcher whose observable seam is the injected FakeTmux (issue-156)."""
    return Dispatcher(
        registry=registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=config,
        tmux_runner=tmux,
    )


def _wait(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


@pytest.fixture
def setup(tmp_path):
    """A dispatcher wired the way the daemon wires it, with control on."""
    registry = SessionRegistry(tmp_path / "local")
    tmux = FakeTmux()
    config = RoutingConfig(
        registry_dir=str(tmp_path / "local"),
        portable_dir=str(tmp_path / "portable"),
        spawn_on_unmatched="labeled",
        auto_execute_label=LABEL,
        spawn_workdir=str(tmp_path),
        control=ControlConfig(),  # defaults: enabled, requireStartCommand
        authorized_users=["octocat"],
    )
    dispatcher = _dispatcher(registry, tmux, config)
    store = ControlStore(str(tmp_path / "portable"))
    yield dispatcher, registry, tmux, store
    dispatcher.stop(timeout=5)


def comment_event(body, delivery="d-1", labels=(LABEL,), author="octocat"):
    payload = {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15, "labels": [{"name": name} for name in labels]},
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
        labeled=False,  # what the poller sets on a comment event
    )


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


def close_event(delivery="c-1"):
    payload = {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15, "labels": []},
    }
    return RoutedEvent(
        event="issues",
        action="closed",
        delivery_id=delivery,
        work_items=extract_work_items("issues", payload),
        payload=payload,
    )


def register(registry, status="active"):
    return registry.register(
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


# -- the label is necessary, not sufficient -------------------------------------


def test_a_labelled_work_item_does_not_spawn_until_it_is_started(setup):
    """
    Feature: authorized execution control
      Scenario: the auto-execute label arms a work item without starting it
        Given a work item carrying the auto-execute label
        And routing.control.requireStartCommand is true
        When the label event reaches the dispatcher
        Then no session is spawned
        And when an authorized user comments the start keyword
        Then a session is spawned for the work item
    Requirement: docs/specs/issue-106/requirements.md AC2.1, AC2.3
    """
    dispatcher, registry, tmux, _ = setup

    dispatcher.handle(labeled_event())
    assert _wait(lambda: True, 0.2)
    assert tmux.spawns == []
    assert registry.find_by_work_item(REF) is None

    dispatcher.handle(comment_event(f"let's go: {START_KEYWORD}", delivery="d-start"))
    # Wait on the REGISTRATION, which is what the next line asserts. Waiting on
    # the spawn instead returns one step early — registration happens after it,
    # on the dispatcher's own thread — so under load the assertion below reads a
    # registry that has not been written yet.
    assert _wait(lambda: registry.find_by_work_item(REF) is not None)
    assert len(tmux.spawns) == 1
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "active"


def opened_event(delivery="o-1", body="", labels=(LABEL,)):
    """A brand-new issue, already carrying the label when it was created."""
    payload = {
        "action": "opened",
        "repository": {"full_name": "octo/repo"},
        "issue": {
            "number": 15,
            "body": body,
            "labels": [{"name": name} for name in labels],
        },
        "sender": {"login": "octocat"},
    }
    return RoutedEvent(
        event="issues",
        action="opened",
        delivery_id=delivery,
        work_items=extract_work_items("issues", payload),
        payload=payload,
        labeled=True,
    )


def test_an_issue_created_with_the_label_still_waits_for_a_start(setup):
    """
    Feature: authorized execution control
      Scenario: creating a work item pre-labelled is arming, not starting
        Given an authorized user opens a NEW issue that already carries the label
        When the opened event reaches the dispatcher
        Then no session is spawned
        And an explicit start command afterwards starts it
    Requirement: docs/specs/issue-106/requirements.md AC2.1, AC2.3
    """
    # Creating a work item with the label on it is the same signal as adding the
    # label to an existing one: it arms, it does not start (owner question on
    # PR #107). Otherwise "open pre-labelled" would be a way to keep the
    # label-is-the-trigger behaviour the whole work item removes.
    dispatcher, registry, tmux, store = setup

    dispatcher.handle(opened_event())
    assert _wait(lambda: True, 0.2)
    assert tmux.spawns == []
    assert registry.find_by_work_item(REF) is None
    assert store.get(REF) is None

    dispatcher.handle(comment_event(START_KEYWORD, delivery="d-start"))
    assert _wait(lambda: len(tmux.spawns) == 1)


def test_a_keyword_in_the_issue_body_is_not_a_command(setup):
    """
    Feature: authorized execution control
      Scenario: the control surface is comments, not the work item's own body
        Given a new labelled issue whose BODY contains the start keyword
        When the opened event reaches the dispatcher
        Then it is not read as a command and nothing is started
    Requirement: docs/specs/issue-106/requirements.md AC1.2
    """
    # The issue/PR body is the text most rewritten (and most quoted from
    # elsewhere), and an `edited` action would re-trigger it. Commands live in
    # comments, where each one is a discrete, attributable, timestamped act.
    dispatcher, registry, tmux, store = setup

    dispatcher.handle(opened_event(body=f"do the thing. {START_KEYWORD}"))
    assert _wait(lambda: True, 0.2)
    assert tmux.spawns == []
    assert store.get(REF) is None


def test_a_start_is_durable_so_a_later_event_can_spawn(setup):
    """
    Feature: authorized execution control
      Scenario: a recorded start survives, so a retried spawn needs no new comment
        Given an authorized user has issued the start command
        When a later labelled event arrives for the same work item
        Then it spawns without the start command being repeated
    Requirement: docs/specs/issue-106/requirements.md AC2.5
    """
    dispatcher, registry, tmux, store = setup
    store.record(REF, "start", source="cli", actor="operator")

    dispatcher.handle(labeled_event(delivery="l-after-start"))
    assert _wait(lambda: len(tmux.spawns) == 1)


def test_a_start_on_an_unlabelled_item_is_refused(setup):
    """
    Feature: authorized execution control
      Scenario: a start cannot conjure a session for an unarmed work item
        Given a work item with no auto-execute label
        When an authorized user comments the start keyword
        Then no session is spawned
    Requirement: docs/specs/issue-106/requirements.md AC2.4
    """
    dispatcher, registry, tmux, store = setup
    dispatcher.handle(comment_event(START_KEYWORD, labels=()))
    assert _wait(lambda: True, 0.2)
    assert tmux.spawns == []
    assert registry.find_by_work_item(REF) is None
    assert store.get(REF) is None  # and nothing is left armed


def test_a_start_on_an_unarmed_item_leaves_nothing_standing(setup):
    """
    Feature: authorized execution control
      Scenario: labelling after a refused start does not start the work item
        Given an authorized user commented the start keyword on an unlabelled item
        And nothing was started
        When the auto-execute label is added afterwards
        Then still nothing is started
        And only a start command issued *after* the label starts it
    Requirement: docs/specs/issue-106/requirements.md AC2.4
    """
    # Owner decision on PR #107: a refused start must not be remembered, or
    # labelling later would start the item — which is the very "labelling is the
    # trigger" behaviour issue-106 removes.
    dispatcher, registry, tmux, store = setup

    # 1. start, with no label
    dispatcher.handle(comment_event(START_KEYWORD, delivery="d-1", labels=()))
    assert store.get(REF) is None
    assert tmux.spawns == []

    # 2. the label is added
    dispatcher.handle(labeled_event(delivery="l-1"))
    assert _wait(lambda: True, 0.2)
    assert tmux.spawns == []
    assert registry.find_by_work_item(REF) is None

    # 3. and only now does a start actually start it
    dispatcher.handle(comment_event(START_KEYWORD, delivery="d-2"))
    assert _wait(lambda: len(tmux.spawns) == 1)


def test_a_resume_with_nothing_to_resume_does_not_arm_the_item(setup):
    """
    Feature: authorized execution control
      Scenario: resume is an arming command, so it too leaves nothing standing
    Requirement: docs/specs/issue-106/requirements.md AC3.6
    """
    dispatcher, registry, tmux, store = setup
    dispatcher.handle(comment_event(RESUME_KEYWORD, delivery="d-r"))
    assert store.get(REF) is None
    dispatcher.handle(labeled_event(delivery="l-r"))
    assert _wait(lambda: True, 0.2)
    assert tmux.spawns == []


def test_a_stop_is_remembered_even_with_no_session(setup):
    """
    Feature: authorized execution control
      Scenario: disarming persists — a stopped work item does not re-spawn
    Requirement: docs/specs/issue-106/requirements.md AC3.6
    """
    dispatcher, registry, tmux, store = setup
    store.record(REF, "start", source="cli", actor="operator")
    dispatcher.handle(comment_event(STOP_KEYWORD, delivery="d-s"))
    record = store.get(REF)
    assert record is not None and record.command == "stop"
    dispatcher.handle(labeled_event(delivery="l-s"))
    assert _wait(lambda: True, 0.2)
    assert tmux.spawns == []


def test_the_pre_106_behaviour_is_one_config_flag_away(tmp_path):
    """
    Feature: authorized execution control
      Scenario: requireStartCommand false restores label-alone spawning
    Requirement: docs/specs/issue-106/requirements.md AC2.6
    """
    registry = SessionRegistry(tmp_path / "sessions")
    tmux = FakeTmux()
    dispatcher = _dispatcher(
        registry,
        tmux,
        RoutingConfig(
            registry_dir=str(tmp_path / "local"),
            portable_dir=str(tmp_path / "portable"),
            spawn_on_unmatched="labeled",
            auto_execute_label=LABEL,
            spawn_workdir=str(tmp_path),
            control=ControlConfig(require_start_command=False),
            authorized_users=["octocat"],
        ),
    )
    try:
        dispatcher.handle(labeled_event())
        assert _wait(lambda: len(tmux.spawns) == 1)
    finally:
        dispatcher.stop(timeout=5)


def test_always_mode_still_waits_for_a_start(tmp_path):
    """
    Feature: authorized execution control
      Scenario: 'always' widens which items may spawn, not who may start them
    Requirement: docs/specs/issue-106/requirements.md AC2.2
    """
    registry = SessionRegistry(tmp_path / "sessions")
    tmux = FakeTmux()
    dispatcher = _dispatcher(
        registry,
        tmux,
        RoutingConfig(
            registry_dir=str(tmp_path / "local"),
            portable_dir=str(tmp_path / "portable"),
            spawn_on_unmatched="always",
            spawn_workdir=str(tmp_path),
        ),
    )
    try:
        dispatcher.handle(labeled_event())
        assert _wait(lambda: True, 0.2)
        assert tmux.spawns == []
    finally:
        dispatcher.stop(timeout=5)


# -- pause / resume / stop ------------------------------------------------------


def test_a_pause_holds_events_and_a_resume_lets_them_through(setup):
    """
    Feature: authorized execution control
      Scenario: pausing suppresses delivery without discarding the session
        Given a running session for a work item
        When an authorized user comments the pause keyword
        Then the session is paused and later comments are not delivered
        And when they comment the resume keyword
        Then the session is active again and comments are delivered
    Requirement: docs/specs/issue-106/requirements.md AC3.2, AC3.3
    """
    dispatcher, registry, tmux, _ = setup
    register(registry)

    dispatcher.handle(comment_event(PAUSE_KEYWORD, delivery="d-pause"))
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "paused"

    dispatcher.handle(comment_event("please rebase", delivery="d-while-paused"))
    assert _wait(lambda: True, 0.2)
    assert tmux.delivers == []

    dispatcher.handle(comment_event(RESUME_KEYWORD, delivery="d-resume"))
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "active"

    dispatcher.handle(comment_event("please rebase now", delivery="d-after"))
    assert _wait(lambda: len(tmux.delivers) == 1)


def test_a_paused_session_is_not_replaced_by_a_second_one(setup):
    """
    Feature: authorized execution control
      Scenario: a paused session still owns its work item
    Requirement: docs/specs/issue-106/requirements.md AC3.7
    """
    dispatcher, registry, tmux, _ = setup
    register(registry, status="paused")
    dispatcher.handle(comment_event(START_KEYWORD, delivery="d-start"))
    assert tmux.spawns == []  # resumed, not re-spawned
    resumed = registry.find_by_work_item(REF)
    assert resumed is not None and resumed.status == "active"


def test_a_stop_closes_the_session(setup):
    """
    Feature: authorized execution control
      Scenario: stopping ends the session through the normal close path
    Requirement: docs/specs/issue-106/requirements.md AC3.4
    """
    dispatcher, registry, tmux, store = setup
    register(registry)

    dispatcher.handle(comment_event(STOP_KEYWORD, delivery="d-stop"))
    assert registry.find_by_work_item(REF) is None
    closed = registry.find_by_work_item(REF, include_closed=True)
    assert closed is not None and closed.status == "closed"
    # …and the stop durably disarms the item, so nothing re-spawns it.
    assert store.start_requested(REF) is False


def test_closing_the_work_item_closes_a_paused_session_too(setup):
    """
    Feature: authorized execution control
      Scenario: a pause never outlives its work item
    Requirement: docs/specs/issue-106/requirements.md AC3.8
    """
    dispatcher, registry, _, store = setup
    register(registry, status="paused")
    store.record(REF, "pause")

    dispatcher.handle(close_event())
    closed = registry.find_by_work_item(REF, include_closed=True)
    assert closed is not None and closed.status == "closed"
    assert store.get(REF) is None  # the ended item's control state is forgotten


def test_a_control_comment_is_never_forwarded_to_the_harness(setup):
    """
    Feature: authorized execution control
      Scenario: a command is executed by the-loop, not read by the agent
    Requirement: docs/specs/issue-106/requirements.md AC1.2
    """
    dispatcher, registry, tmux, _ = setup
    register(registry)
    dispatcher.handle(comment_event(f"{PAUSE_KEYWORD} please", delivery="d-1"))
    assert _wait(lambda: True, 0.2)
    assert tmux.delivers == []


def test_an_ambiguous_comment_does_nothing_at_all(setup):
    """
    Feature: authorized execution control
      Scenario: two conflicting keywords execute nothing and forward nothing
    Requirement: docs/specs/issue-106/requirements.md AC1.4
    """
    dispatcher, registry, tmux, store = setup
    register(registry)
    dispatcher.handle(
        comment_event(f"{PAUSE_KEYWORD} then {STOP_KEYWORD}", delivery="d-amb")
    )
    assert _wait(lambda: True, 0.2)
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "active"
    assert tmux.delivers == []
    assert store.get(REF) is None


def test_a_command_needs_a_named_authorized_actor(setup):
    """
    Feature: authorized execution control
      Scenario: an actor-less comment cannot execute a command
        Given a comment carrying the stop keyword whose author is unknown
        When the dispatcher handles it
        Then no command runs and the session is untouched
    Requirement: docs/specs/issue-106/requirements.md AC1.6, AC2.7
    """
    # `is_authorized` deliberately allows an actor-less *action* (a CI event
    # carries status, not instructions) — a comment by a deleted account reaches
    # the dispatcher the same way on the poll path. Harmless as agent input;
    # not harmless as a command, so the control path re-checks.
    dispatcher, registry, tmux, store = setup
    register(registry)
    dispatcher.handle(comment_event(STOP_KEYWORD, delivery="d-ghost", author=""))
    assert registry.find_by_work_item(REF) is not None
    assert store.get(REF) is None


def test_a_command_from_a_login_outside_the_allowlist_is_refused(setup):
    """
    Feature: authorized execution control
      Scenario: the control path is gated by the same allowlist as everything else
    Requirement: docs/specs/issue-106/requirements.md AC1.6
    """
    dispatcher, registry, tmux, store = setup
    register(registry)
    dispatcher.handle(comment_event(STOP_KEYWORD, delivery="d-x", author="stranger"))
    assert registry.find_by_work_item(REF) is not None
    assert store.get(REF) is None


def test_an_ordinary_comment_still_reaches_the_session(setup):
    """
    Feature: authorized execution control
      Scenario: control parsing does not disturb normal event delivery
    Requirement: docs/specs/issue-106/requirements.md AC1.7
    """
    dispatcher, registry, tmux, _ = setup
    register(registry)
    dispatcher.handle(comment_event("could you rebase?", delivery="d-plain"))
    assert _wait(lambda: len(tmux.delivers) == 1)


def test_control_disabled_forwards_the_keyword_as_a_plain_comment(tmp_path):
    """
    Feature: authorized execution control
      Scenario: routing.control.enabled false is the pre-issue-106 behaviour
    Requirement: docs/specs/issue-106/requirements.md AC1.7
    """
    registry = SessionRegistry(tmp_path / "sessions")
    tmux = FakeTmux()
    dispatcher = _dispatcher(
        registry,
        tmux,
        RoutingConfig(
            registry_dir=str(tmp_path / "local"),
            portable_dir=str(tmp_path / "portable"),
            control=ControlConfig(enabled=False),
            authorized_users=["octocat"],
        ),
    )
    register(registry)
    try:
        dispatcher.handle(comment_event(PAUSE_KEYWORD, delivery="d-off"))
        assert _wait(lambda: len(tmux.delivers) == 1)
        session = registry.find_by_work_item(REF)
        assert session is not None and session.status == "active"
    finally:
        dispatcher.stop(timeout=5)


# -- the poller does not arm what nobody started --------------------------------


class _Provider(PollProvider):
    """Minimal in-process provider: one labelled item, one comment thread."""

    name = "fake"

    def __init__(self, comments=()):
        self.item = WorkItem(
            provider="github",
            owner="octo",
            repo="repo",
            number=15,
            kind="issue",
            author="octocat",
            labels=[LABEL],
        )
        self._comments = list(comments)
        self.presence_events = 0

    def list_work_items(self):
        return [self.item]

    def list_comments(self, item):
        return list(self._comments)

    def refs(self, item):
        return [WorkItemRef.parse(REF)]

    def presence_event(self, item, refs):
        self.presence_events += 1
        return labeled_event(delivery=f"presence-{self.presence_events}")

    def comment_event(self, item, comment, refs):
        return comment_event(comment.body, delivery=f"comment-{comment.id}")


def _poller(tmp_path, dispatcher, provider):
    return Poller(
        providers=[provider],
        registry=dispatcher.registry,
        dispatcher=dispatcher,
        config=PollConfig(),
        state=PollState(WorkItemStore(tmp_path / "portable")),
        authorized_users=["octocat"],
    )


def test_the_poller_does_not_arm_a_spawn_for_an_unstarted_item(setup, tmp_path):
    """
    Feature: authorized execution control
      Scenario: the poller stops offering presence events nobody asked for
        Given a labelled work item that has never been started
        When the poller runs a cycle
        Then it emits no presence event (and burns no retry budget)
    Requirement: docs/specs/issue-106/requirements.md AC2.1
    """
    dispatcher, registry, tmux, _ = setup
    provider = _Provider()
    poller = _poller(tmp_path, dispatcher, provider)

    summary = poller.poll_once()
    assert provider.presence_events == 0
    assert summary.spawns == 0
    assert summary.failures == 0
    assert registry.find_by_work_item(REF) is None


def test_the_poller_arms_once_the_item_has_been_started(setup, tmp_path):
    """
    Feature: authorized execution control
      Scenario: a started work item is spawned by the next poll cycle
    Requirement: docs/specs/issue-106/requirements.md AC2.3, AC2.5
    """
    dispatcher, registry, tmux, store = setup
    store.record(REF, "start", source="cli", actor="operator")
    provider = _Provider()
    poller = _poller(tmp_path, dispatcher, provider)

    poller.poll_once()
    assert provider.presence_events == 1
    assert _wait(lambda: len(tmux.spawns) == 1)


def test_a_start_comment_spawns_through_the_poll_path(setup, tmp_path):
    """
    Feature: authorized execution control
      Scenario: the start command reaches the dispatcher as an ordinary comment
        Given a labelled item the poller has already baselined
        When an authorized user posts the start keyword
        Then the next poll cycle forwards it and a session is spawned
    Requirement: docs/specs/issue-106/requirements.md AC1.5, AC2.3
    """
    dispatcher, registry, tmux, _ = setup
    provider = _Provider()
    poller = _poller(tmp_path, dispatcher, provider)
    poller.poll_once()  # first sight: baseline the (empty) thread

    provider._comments = [
        Comment(
            id="c1",
            body=START_KEYWORD,
            author="octocat",
            created_at="2026-07-26T00:00:00Z",
            url="https://c/1",
        )
    ]
    poller.poll_once()
    assert _wait(lambda: len(tmux.spawns) == 1)
    assert provider.presence_events == 0  # the comment spawned it, not presence


# -- a start that predates first sight (issue-119) ------------------------------


def _comment(cid, body, author="octocat"):
    return Comment(
        id=cid,
        body=body,
        author=author,
        created_at="2026-07-30T16:47:24Z",
        url=f"https://c/{cid}",
    )


def test_a_start_comment_that_predates_first_sight_still_starts_the_item(
    setup, tmp_path
):
    """
    Feature: authorized execution control
      Scenario: the start command is already on the thread the first time the
                poller sees the work item
        Given a labelled work item the poller has never seen
        And its thread already carries an authorized start keyword
        When the poller runs its first cycle over it
        Then the start is recorded and a session is spawned
        And no presence event is emitted for it
    Requirement: docs/specs/issue-119/requirements.md AC1, AC3, AC8
    """
    dispatcher, registry, tmux, store = setup
    provider = _Provider(comments=[_comment("c1", START_KEYWORD)])
    poller = _poller(tmp_path, dispatcher, provider)

    poller.poll_once()

    assert _wait(lambda: len(tmux.spawns) == 1)
    record = store.get(REF)
    assert record is not None and record.command == "start"
    assert provider.presence_events == 0  # the comment started it, not the label


def _recorded(store, ref=REF):
    record = store.get(ref)
    return record.command if record is not None else ""


def test_pre_existing_control_comments_are_applied_in_thread_order(setup, tmp_path):
    """
    Feature: authorized execution control
      Scenario: a first-sight thread carrying start then stop ends disarmed
        Given a labelled work item the poller has never seen
        And its thread carries the start keyword followed by the stop keyword
        When the poller runs its first cycle over it
        Then both are applied in thread order, so the recorded state is stop
    Requirement: docs/specs/issue-119/requirements.md AC2
    """
    dispatcher, registry, tmux, store = setup
    provider = _Provider(
        comments=[_comment("c1", START_KEYWORD), _comment("c2", STOP_KEYWORD)]
    )
    poller = _poller(tmp_path, dispatcher, provider)

    poller.poll_once()

    # The last command on the thread wins — the item is left disarmed, so the
    # next cycle does not re-arm it. (Whether the in-flight spawn the start
    # queued lands before the stop is the dispatcher's pre-existing async
    # behaviour, identical on the webhook path; this asserts the ordering the
    # poller is responsible for.)
    assert _recorded(store) == "stop"


def test_a_stop_that_predates_first_sight_leaves_the_item_disarmed(setup, tmp_path):
    """
    Feature: authorized execution control
      Scenario: a pre-existing stop is honoured, not discarded
    Requirement: docs/specs/issue-119/requirements.md AC2
    """
    dispatcher, registry, tmux, store = setup
    provider = _Provider(comments=[_comment("c1", STOP_KEYWORD)])
    poller = _poller(tmp_path, dispatcher, provider)

    poller.poll_once()

    assert _recorded(store) == "stop"
    assert _wait(lambda: True, 0.2)
    assert tmux.spawns == []
    assert provider.presence_events == 0
