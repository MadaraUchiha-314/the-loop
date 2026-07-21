"""Integration tests: gh poll → GitHub provider → dispatcher → harness spawn.

Unlike ``test_poller.py`` (which asserts on synthesised events via doubles),
these drive the *real* GitHub provider and the *real* Dispatcher — a poll cycle
actually spawns and registers a session and a later cycle actually resumes it —
so they prove the provider-agnostic poller reuses the webhook routing/dispatch
stack end to end, including the one-session-per-work-item guarantee.

Feature: Poll GitHub and spawn/route harness sessions
Requirement: docs/specs/issue-34/requirements.md#R1
"""

import json
import subprocess
import threading
import time

from the_loop.harness import DispatchResult
from the_loop.poller import (
    GhClient,
    GitHubPollProvider,
    PollConfig,
    Poller,
    PollState,
    parse_repos,
)
from the_loop.sessions import SessionRegistry
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig

LABEL = "the-loop: auto-execute"
REF = "github:octo/repo#15"


def wait_until(predicate, timeout=5.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class FakeAdapter:
    """In-process HarnessAdapter double recording spawns and resumes."""

    name = "claude"

    def __init__(self, spawn_id="spawned-1"):
        self.spawn_id = spawn_id
        self.spawns = []
        self.resumes = []
        self._lock = threading.Lock()

    def is_available(self):
        return True

    def spawn(self, work_item, prompt, cwd, timeout=None):
        with self._lock:
            self.spawns.append((work_item.ref, prompt, cwd))
        return DispatchResult(ok=True, session_id=self.spawn_id)

    def resume(self, session, prompt, timeout=None):
        with self._lock:
            self.resumes.append((session.work_item.ref, prompt))
        return DispatchResult(ok=True, session_id=session.harness_session_id)


class GhState:
    """Mutable canned gh responses shared across poll cycles."""

    def __init__(self):
        self.issues = [
            {"number": 15, "title": "i", "labels": [{"name": LABEL}], "url": "u"}
        ]
        self.comments = []

    def runner(self, cmd, **kwargs):
        sub = (cmd[1], cmd[2])
        if sub == ("issue", "list"):
            out = json.dumps(self.issues)
        elif sub == ("pr", "list"):
            out = json.dumps([])
        else:  # issue view --json comments
            out = json.dumps({"comments": self.comments})
        return subprocess.CompletedProcess(cmd, 0, out, "")


def _comment(cid, body):
    return {
        "id": cid,
        "body": body,
        "author": {"login": "octocat"},
        "createdAt": "",
        "url": "u",
    }


def _dispatcher(registry, adapter, config):
    # adapter intentionally unannotated so the in-process FakeAdapter double
    # satisfies Dict[str, HarnessAdapter] (mirrors test_routing.make_dispatcher).
    return Dispatcher(registry=registry, adapters={"claude": adapter}, config=config)


def _make(tmp_path, gh_state):
    registry = SessionRegistry(tmp_path / "sessions")
    adapter = FakeAdapter()
    dispatcher = _dispatcher(
        registry, adapter, RoutingConfig(spawn_on_unmatched="labeled")
    )
    provider = GitHubPollProvider(
        parse_repos(["octo/repo"]),
        LABEL,
        monitor_prs=False,
        gh=GhClient(runner=gh_state.runner),
    )
    poller = Poller(
        providers=[provider],
        registry=registry,
        dispatcher=dispatcher,
        config=PollConfig(),
        state=PollState(tmp_path / "state.json"),
    )
    return registry, adapter, dispatcher, poller


def test_labeled_issue_spawns_a_registered_session_once(tmp_path):
    """Scenario: a labelled issue with no session gets one, and only one.

    Given a labelled issue with no registered session
    When two poll cycles run
    Then a single harness session is spawned and registered for it
    """
    registry, adapter, dispatcher, poller = _make(tmp_path, GhState())

    poller.poll_once()
    assert wait_until(lambda: len(adapter.spawns) == 1)
    poller.poll_once()  # registry now has it -> must not spawn again
    time.sleep(0.1)
    dispatcher.stop()

    assert len(adapter.spawns) == 1
    session = registry.find_by_work_item(REF)
    assert session is not None and session.harness_session_id == "spawned-1"
    _, prompt, _ = adapter.spawns[0]
    assert "/the-loop:work-on" in prompt and REF in prompt


def test_new_comment_after_spawn_resumes_same_session(tmp_path):
    """Scenario: a new comment on an already-worked item resumes its session.

    Given a labelled issue that already spawned a session
    When a new comment appears and the next poll cycle runs
    Then the existing session is resumed with the comment (no new spawn)
    """
    gh = GhState()
    gh.comments = [_comment("IC_1", "old")]
    registry, adapter, dispatcher, poller = _make(tmp_path, gh)

    poller.poll_once()  # spawn + baseline IC_1
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)

    gh.comments = [_comment("IC_1", "old"), _comment("IC_2", "the build is red")]
    poller.poll_once()  # forward IC_2 only
    assert wait_until(lambda: len(adapter.resumes) == 1)
    dispatcher.stop()

    assert len(adapter.spawns) == 1  # no duplicate spawn
    ref, prompt = adapter.resumes[0]
    assert ref == REF
    assert "the build is red" in prompt and "UNTRUSTED" in prompt


def test_comment_not_reforwarded_across_cycles(tmp_path):
    """Scenario: the same comment is delivered at most once.

    Given a session and a comment already forwarded
    When further poll cycles run with no new comments
    Then the comment is not resumed again (durable dedup)
    """
    gh = GhState()
    gh.comments = [_comment("IC_1", "baseline")]
    registry, adapter, dispatcher, poller = _make(tmp_path, gh)

    poller.poll_once()
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)
    gh.comments = [_comment("IC_1", "baseline"), _comment("IC_2", "fix it")]
    poller.poll_once()
    assert wait_until(lambda: len(adapter.resumes) == 1)
    poller.poll_once()  # no new comments
    poller.poll_once()
    time.sleep(0.1)
    dispatcher.stop()

    assert len(adapter.resumes) == 1  # IC_2 delivered exactly once


def test_run_once_stops_after_a_single_cycle(tmp_path):
    _, adapter, dispatcher, poller = _make(tmp_path, GhState())
    poller.run(once=True, stop_event=threading.Event())
    assert wait_until(lambda: len(adapter.spawns) == 1)
    dispatcher.stop()
