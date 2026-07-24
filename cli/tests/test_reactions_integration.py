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

from the_loop import reactions as reactions_mod
from the_loop.harness.base import DispatchResult
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


class FakeAdapter:
    """In-process harness double with a scriptable resume outcome."""

    name = "claude"

    def __init__(self, resume_ok=True):
        self.resume_ok = resume_ok
        self.calls = []
        self.spawns = []

    def is_available(self):
        return True

    def resume(self, session, prompt, timeout=None):
        self.calls.append((session.work_item.ref, prompt))
        if self.resume_ok:
            return DispatchResult(ok=True, session_id=session.harness_session_id)
        return DispatchResult(ok=False, error="harness exploded")

    def spawn(self, work_item, prompt, cwd, timeout=None):
        self.spawns.append((work_item.ref, prompt, cwd))
        return DispatchResult(ok=True, session_id="spawned-1")


class RecordingRunner:
    """Captures every gh argv the reactor runs; always succeeds."""

    def __init__(self):
        self.commands = []

    def __call__(self, cmd, capture_output=True, text=True, timeout=None):
        self.commands.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def make_dispatcher(tmp_path, adapter, monkeypatch, reactions=None, **config_overrides):
    monkeypatch.setattr(reactions_mod.shutil, "which", lambda _: "/usr/bin/gh")
    runner = RecordingRunner()
    config = RoutingConfig(
        reactions=reactions or ReactionConfig(enabled=True), **config_overrides
    )
    dispatcher = Dispatcher(
        registry=SessionRegistry(tmp_path / "sessions"),
        adapters={"claude": adapter},
        config=config,
        reactor=GitHubReactor(config=config.reactions, runner=runner),
    )
    return dispatcher, runner


def make_session(ref=REF):
    return Session(
        work_item=WorkItemRef.parse(ref),
        harness="claude",
        harness_session_id="sess-1",
        cwd=".",
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
      When an issue_comment event is dispatched and the harness resume succeeds
      Then the triggering comment receives the started reaction (eyes)
      And then the completed reaction (hooray)
    Requirement: docs/specs/issue-84/requirements.md#requirement-1
    """
    adapter = FakeAdapter(resume_ok=True)
    dispatcher, runner = make_dispatcher(tmp_path, adapter, monkeypatch)
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
      Given a registered session whose harness resume fails
      When the issue_comment event is dispatched
      Then the comment receives the started reaction (eyes)
      And then the error reaction (confused)
      And the dispatch failure handling (delivery release) is unchanged
    Requirement: docs/specs/issue-84/requirements.md#requirement-1
    """
    adapter = FakeAdapter(resume_ok=False)
    dispatcher, runner = make_dispatcher(tmp_path, adapter, monkeypatch)
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
    adapter = FakeAdapter()
    dispatcher, runner = make_dispatcher(
        tmp_path, adapter, monkeypatch, spawn_on_unmatched="labeled"
    )
    dispatcher.handle(routed_labeled_issue())
    assert wait_until(lambda: len(runner.commands) == 2)
    dispatcher.stop()
    assert len(adapter.spawns) == 1
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
    adapter = FakeAdapter()
    dispatcher, runner = make_dispatcher(tmp_path, adapter, monkeypatch)
    dispatcher.handle(routed_comment(delivery="drop-1"))  # unmatched → dropped
    dispatcher.stop()
    assert runner.commands == []

    dispatcher, runner = make_dispatcher(tmp_path, adapter, monkeypatch)
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
    adapter = FakeAdapter()
    dispatcher, runner = make_dispatcher(
        tmp_path,
        adapter,
        monkeypatch,
        reactions=ReactionConfig(enabled=False),
    )
    dispatcher.registry.register(make_session())
    dispatcher.handle(routed_comment())
    assert wait_until(lambda: len(adapter.calls) == 1)
    dispatcher.stop()
    assert runner.commands == []
