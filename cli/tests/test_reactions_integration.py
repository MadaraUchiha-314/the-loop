"""Integration tests: routed event → dispatcher → real reactor → gh argv.

Feature: Dispatch-lifecycle emoji reactions
Requirement: docs/specs/issue-84/requirements.md

Each scenario drives the real ``Dispatcher`` worker with a real
``GitHubReactor`` whose ``gh`` invocation is captured by a fake runner — so
they prove which reactions are actually posted, in which order, and on which
GitHub entity, for each dispatch outcome.
"""

import subprocess
import time

from conftest import FakeTmux, StubInteractiveAdapter
from the_loop.control import ControlConfig
from the_loop.instance import InstanceConfig
from the_loop import reactions as reactions_mod
from the_loop.reactions import GitHubReactor, ReactionConfig
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent, extract_work_items

REF = "github:octo/repo#15"
LABEL = "the-loop: auto-execute"


def wait_until(predicate, timeout=5.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class RecordingRunner:
    """Captures every gh argv the reactor runs; always succeeds."""

    def __init__(self):
        self.commands = []

    def __call__(self, cmd, capture_output=True, text=True, timeout=None):
        self.commands.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def make_dispatcher(tmp_path, tmux, monkeypatch, reactions=None, **config_overrides):
    monkeypatch.setattr(reactions_mod.shutil, "which", lambda _: "/usr/bin/gh")
    runner = RecordingRunner()
    config_overrides.setdefault(
        # Pre-issue-106 spawn behaviour (the start gate has its own tests).
        "control",
        ControlConfig(require_start_command=False),
    )
    config = RoutingConfig(
        reactions=reactions or ReactionConfig(enabled=True), **config_overrides
    )
    dispatcher = Dispatcher(
        registry=SessionRegistry(tmp_path / "sessions"),
        adapters={"claude": StubInteractiveAdapter()},
        config=config,
        tmux_runner=tmux,
        reactor=GitHubReactor(config=config.reactions, runner=runner),
    )
    return dispatcher, runner


def make_session(ref=REF):
    return Session(
        work_item=WorkItemRef.parse(ref),
        harness="claude",
        harness_session_id="sess-1",
        cwd=".",
        tmux_target="loop-github-octo-repo-15",
    )


def routed_comment(delivery="d-1", comment_id=123):
    payload = {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15},
        "comment": {"id": comment_id, "body": "please fix"},
    }
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id=delivery,
        work_items=extract_work_items("issue_comment", payload),
        payload=payload,
    )


def routed_labeled_issue(delivery="l-1"):
    payload = {
        "action": "labeled",
        "label": {"name": LABEL},
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15},
    }
    return RoutedEvent(
        event="issues",
        action="labeled",
        delivery_id=delivery,
        work_items=extract_work_items("issues", payload),
        payload=payload,
        labeled=True,
    )


def contents(runner):
    """The reaction content of each captured gh call, in order."""
    out = []
    for cmd in runner.commands:
        out.append(next(a for a in cmd if a.startswith("content=")))
    return out


def test_successful_dispatch_reacts_started_then_completed_on_comment(
    tmp_path, monkeypatch
):
    """
    Feature: Dispatch-lifecycle emoji reactions
    Scenario: A routed comment is dispatched successfully
      Given a registered session for the work item
      And reactions are enabled with the default palette
      When an issue_comment event is dispatched and the tmux delivery succeeds
      Then the triggering comment receives the started reaction (eyes)
      And then the completed reaction (hooray)
    Requirement: docs/specs/issue-84/requirements.md#requirement-1
    """
    tmux = FakeTmux()
    dispatcher, runner = make_dispatcher(tmp_path, tmux, monkeypatch)
    dispatcher.registry.register(make_session())
    dispatcher.handle(routed_comment())
    assert wait_until(lambda: len(runner.commands) == 2)
    dispatcher.stop()
    assert contents(runner) == ["content=eyes", "content=hooray"]
    for cmd in runner.commands:  # both landed on the comment, not the issue
        assert "repos/octo/repo/issues/comments/123/reactions" in cmd


def test_failed_dispatch_reacts_started_then_error(tmp_path, monkeypatch):
    """
    Feature: Dispatch-lifecycle emoji reactions
    Scenario: A routed comment's dispatch fails
      Given a registered session whose tmux delivery fails
      When the issue_comment event is dispatched
      Then the comment receives the started reaction (eyes)
      And then the error reaction (confused)
      And the dispatch failure handling (delivery release) is unchanged
    Requirement: docs/specs/issue-84/requirements.md#requirement-1
    """
    tmux = FakeTmux()
    tmux.deliver_ok = False  # transient delivery failure
    dispatcher, runner = make_dispatcher(tmp_path, tmux, monkeypatch)
    dispatcher.registry.register(make_session())
    dispatcher.handle(routed_comment(delivery="fail-1"))
    assert wait_until(lambda: len(runner.commands) == 2)
    dispatcher.stop()
    assert contents(runner) == ["content=eyes", "content=confused"]
    assert "fail-1" not in dispatcher.deduper  # released for redelivery, as before


def test_labeled_spawn_reacts_on_the_issue_itself(tmp_path, monkeypatch):
    """
    Feature: Dispatch-lifecycle emoji reactions
    Scenario: An auto-execute label spawns a session
      Given no session exists and spawnOnUnmatched is labeled
      When a labeled issues event arrives
      Then the issue itself receives the started and completed reactions
      Because a presence event carries no comment to react on
    Requirement: docs/specs/issue-84/requirements.md#requirement-1
    """
    tmux = FakeTmux()
    dispatcher, runner = make_dispatcher(
        tmp_path, tmux, monkeypatch, spawn_on_unmatched="labeled"
    )
    dispatcher.handle(routed_labeled_issue())
    assert wait_until(lambda: len(runner.commands) == 2)
    dispatcher.stop()
    assert len(tmux.spawns) == 1
    assert contents(runner) == ["content=eyes", "content=hooray"]
    for cmd in runner.commands:
        assert "repos/octo/repo/issues/15/reactions" in cmd


def test_unprocessed_events_get_no_reaction(tmp_path, monkeypatch):
    """
    Feature: Dispatch-lifecycle emoji reactions
    Scenario: Events the-loop does not process are not acknowledged
      Given no session exists and spawnOnUnmatched is never
      When a comment event arrives (dropped by spawn policy)
      And a duplicate of an already-dispatched delivery arrives
      Then no reaction is posted for the dropped and duplicate events
    Requirement: docs/specs/issue-84/requirements.md#requirement-1
    """
    tmux = FakeTmux()
    dispatcher, runner = make_dispatcher(tmp_path, tmux, monkeypatch)
    dispatcher.handle(routed_comment(delivery="drop-1"))  # unmatched → dropped
    dispatcher.stop()
    assert runner.commands == []

    dispatcher, runner = make_dispatcher(tmp_path, tmux, monkeypatch)
    dispatcher.registry.register(make_session())
    dispatcher.handle(routed_comment(delivery="dup-1"))
    dispatcher.handle(routed_comment(delivery="dup-1"))  # duplicate → dropped
    assert wait_until(lambda: len(runner.commands) >= 2)
    time.sleep(0.1)  # give a would-be duplicate time to (wrongly) react
    dispatcher.stop()
    assert contents(runner) == ["content=eyes", "content=hooray"]  # one event only


def test_reactions_disabled_posts_nothing(tmp_path, monkeypatch):
    """
    Feature: Dispatch-lifecycle emoji reactions
    Scenario: The operator opts out
      Given routing.reactions.enabled is false
      When a comment event is dispatched successfully
      Then no gh invocation happens at all
    Requirement: docs/specs/issue-84/requirements.md#requirement-2
    """
    tmux = FakeTmux()
    dispatcher, runner = make_dispatcher(
        tmp_path,
        tmux,
        monkeypatch,
        reactions=ReactionConfig(enabled=False),
    )
    dispatcher.registry.register(make_session())
    dispatcher.handle(routed_comment())
    assert wait_until(lambda: len(tmux.delivers) == 1)
    dispatcher.stop()
    assert runner.commands == []


# -- the consumed branch (issue-371) -------------------------------------------
#
# Everything above drives an event the dispatcher *delivers*. These drive the
# other branch: an event it consumes as an instruction to itself, or refuses on
# purpose. Before issue-371 none of them was acknowledged at all — the reported
# bug being `the-loop add-collaborator @someone`, which writes a roster and
# returns, leaving the person who typed it with an unmarked comment.


def make_control_dispatcher(tmp_path, tmux, monkeypatch, **overrides):
    """A dispatcher with control ON and an allow-listed human (issue-371)."""
    overrides.setdefault("control", ControlConfig())
    overrides.setdefault("authorized_users", ["octocat"])
    overrides.setdefault("spawn_on_unmatched", "labeled")
    overrides.setdefault("auto_execute_labels", [LABEL])
    overrides.setdefault("registry_dir", str(tmp_path / "sessions"))
    overrides.setdefault("portable_dir", str(tmp_path / "portable"))
    overrides.setdefault("spawn_workdir", str(tmp_path))
    return make_dispatcher(tmp_path, tmux, monkeypatch, **overrides)


def routed_command(
    body, delivery="k-1", labels=(LABEL,), author="octocat", body_extra=""
):
    payload = {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15, "labels": [{"name": name} for name in labels]},
        "comment": {
            "id": 77,
            "body": f"{body}{body_extra}",
            "html_url": "https://c/77",
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


def test_a_grant_is_acknowledged_on_the_comment_that_carried_it(tmp_path, monkeypatch):
    """
    Feature: Acknowledging the events the-loop consumes
    Scenario: `the-loop add-collaborator` gets the completed reaction
      Given control is enabled and octocat is an authorized user
      When octocat comments the add-collaborator keyword naming @dana
      Then dana is on the work item's roster
      And the comment that carried the command receives the completed reaction
      And nothing is delivered to a session, because the comment WAS the command
    Requirement: docs/specs/issue-371/requirements.md#r1--an-event-the-dispatcher-finishes-with-is-acknowledged-on-the-entity-it-arrived-on
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)

    dispatcher.handle(routed_command("the-loop add-collaborator @Dana"))
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.stop()

    assert dispatcher.collaborator_store.logins(REF) == ["dana"]
    assert contents(runner) == ["content=hooray"]
    assert "repos/octo/repo/issues/comments/77/reactions" in runner.commands[0]
    assert tmux.delivers == [] and tmux.spawns == []


def test_an_executed_session_command_is_acknowledged(tmp_path, monkeypatch):
    """
    Feature: Acknowledging the events the-loop consumes
    Scenario: `the-loop pause` gets the completed reaction
      Given a registered session for the work item
      When an authorized user comments the pause keyword
      Then the session is paused
      And the comment receives the completed reaction, once
    Requirement: docs/specs/issue-371/requirements.md#r1--an-event-the-dispatcher-finishes-with-is-acknowledged-on-the-entity-it-arrived-on
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)
    dispatcher.registry.register(make_session())

    dispatcher.handle(routed_command("the-loop pause", delivery="k-2"))
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.stop()

    paused = dispatcher.registry.find_by_work_item(REF)
    assert paused is not None and paused.is_paused
    assert contents(runner) == ["content=hooray"]


def test_a_refused_command_is_acknowledged_with_the_error_reaction(
    tmp_path, monkeypatch
):
    """
    Feature: Acknowledging the events the-loop consumes
    Scenario: `the-loop start` on a work item that is not armed
      Given spawnOnUnmatched is labeled and the work item carries no label
      When an authorized user comments the start keyword
      Then nothing is spawned
      And the comment receives the error reaction, so the refusal is visible
    Requirement: docs/specs/issue-371/requirements.md#r1--an-event-the-dispatcher-finishes-with-is-acknowledged-on-the-entity-it-arrived-on
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)

    dispatcher.handle(routed_command("the-loop start", delivery="k-3", labels=()))
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.stop()

    assert tmux.spawns == []
    assert contents(runner) == ["content=confused"]
    assert dispatcher.delivery_outcome("k-3") == "control-rejected"


def test_conflicting_keywords_are_acknowledged_with_the_error_reaction(
    tmp_path, monkeypatch
):
    """
    Feature: Acknowledging the events the-loop consumes
    Scenario: One comment carries two different control keywords
      Given control is enabled
      When an authorized user comments both the start and the stop keyword
      Then neither is executed
      And the comment receives the error reaction rather than silence
    Requirement: docs/specs/issue-371/requirements.md#r1--an-event-the-dispatcher-finishes-with-is-acknowledged-on-the-entity-it-arrived-on
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)
    dispatcher.registry.register(make_session())

    dispatcher.handle(
        routed_command("the-loop start", delivery="k-4", body_extra=" the-loop stop")
    )
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.stop()

    assert tmux.delivers == [] and tmux.spawns == []
    assert contents(runner) == ["content=confused"]
    assert dispatcher.delivery_outcome("k-4") == "control-ambiguous"


def test_a_suppressed_comment_is_acknowledged_as_seen(tmp_path, monkeypatch):
    """
    Feature: Acknowledging the events the-loop consumes
    Scenario: A comment on an armed work item nobody has started
      Given requireStartCommand is on and no session exists
      When an authorized user comments ordinary prose on the labelled work item
      Then nothing is spawned and nothing is delivered
      And the comment receives the started reaction — seen, not failed, because
        the harness re-reads the thread once the work item is started
    Requirement: docs/specs/issue-371/requirements.md#r1--an-event-the-dispatcher-finishes-with-is-acknowledged-on-the-entity-it-arrived-on
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)

    dispatcher.handle(routed_command("please have a look at this", delivery="k-5"))
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.stop()

    assert tmux.spawns == [] and tmux.delivers == []
    assert contents(runner) == ["content=eyes"]
    assert dispatcher.delivery_outcome("k-5") == "awaiting-start"


def test_an_out_of_scope_refusal_leaves_no_mark(tmp_path, monkeypatch):
    """
    Feature: Acknowledging the events the-loop consumes
    Scenario: Another instance was addressed
      Given this instance is named alpha
      When a comment addressed to instance:beta arrives, with and without an
        authorized control keyword
      Then neither posts any reaction at all
      Because a mark from a non-owner instance is noise on the thread and could
        have two daemons appear to steer one work item
    Requirement: docs/specs/issue-371/requirements.md#r2--acknowledging-never-changes-what-the-dispatcher-does
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(
        tmp_path, tmux, monkeypatch, instance=InstanceConfig(name="alpha")
    )

    dispatcher.handle(routed_command("the-loop pause instance:beta", delivery="k-6"))
    dispatcher.handle(routed_command("just a note instance:beta", delivery="k-7"))
    dispatcher.stop()

    assert runner.commands == []
    # The command route settles as a rejection — the outcome that maps to 😕 —
    # so the silence here is the `acknowledge=False` the scope refusal passes,
    # not an accident of the table.
    assert dispatcher.delivery_outcome("k-6") == "control-rejected"
    assert dispatcher.delivery_outcome("k-7") == "addressed-elsewhere"


def test_the_silent_drops_stay_silent(tmp_path, monkeypatch):
    """
    Feature: Acknowledging the events the-loop consumes
    Scenario: Events the-loop never decided about
      Given control is enabled
      When a comment arrives on a work item the spawn policy does not arm
      And a duplicate of an already-settled delivery arrives
      Then no reaction is posted for either
      Because a policy drop is released for retry — the-loop is not finished
        with it — and a duplicate was acknowledged on its first delivery
    Requirement: docs/specs/issue-371/requirements.md#r2--acknowledging-never-changes-what-the-dispatcher-does
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)

    # Unlabelled, no command: refused by spawn policy and released, not settled.
    dispatcher.handle(routed_command("hello there", delivery="k-8", labels=()))
    dispatcher.stop()
    assert runner.commands == []

    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)
    dispatcher.handle(routed_command("the-loop add-collaborator @dana", delivery="k-9"))
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.handle(routed_command("the-loop add-collaborator @dana", delivery="k-9"))
    time.sleep(0.1)  # give a would-be duplicate time to (wrongly) react
    dispatcher.stop()
    assert contents(runner) == ["content=hooray"]


def test_the_in_worker_settle_adds_no_reaction(tmp_path, monkeypatch):
    """
    Feature: Acknowledging the events the-loop consumes
    Scenario: A session paused between enqueue and dequeue
      Given an event already queued for a session that is then paused
      When the dispatch runs and settles the delivery as session-paused
      Then that settle posts nothing
      Because it happens inside the delivered branch, whose worker has already
        reacted on this entity and reacts again from the dispatch outcome
    Requirement: docs/specs/issue-371/requirements.md#r2--acknowledging-never-changes-what-the-dispatcher-does
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)
    dispatcher.registry.register(make_session())
    dispatcher.registry.pause(WorkItemRef.parse(REF))
    routed = routed_command("please look", delivery="k-10")
    dispatcher.deduper.add("k-10")

    assert dispatcher._dispatch_one(REF, routed, False) is True
    dispatcher.stop()

    assert runner.commands == []  # the worker's own two calls are the whole story
    assert dispatcher.delivery_outcome("k-10") == "session-paused"


def test_disabled_reactions_silence_the_consumed_branch_too(tmp_path, monkeypatch):
    """
    Feature: Acknowledging the events the-loop consumes
    Scenario: The operator opts out
      Given routing.reactions.enabled is false
      When an authorized user comments the add-collaborator keyword
      Then the roster is written and no gh invocation happens at all
    Requirement: docs/specs/issue-371/requirements.md#r2--acknowledging-never-changes-what-the-dispatcher-does
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(
        tmp_path, tmux, monkeypatch, reactions=ReactionConfig(enabled=False)
    )

    dispatcher.handle(
        routed_command("the-loop add-collaborator @dana", delivery="k-11")
    )
    assert wait_until(lambda: dispatcher.collaborator_store.logins(REF) == ["dana"])
    dispatcher.stop()

    assert runner.commands == []
