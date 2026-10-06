"""Integration tests: the CI gate inside the dispatcher (issue-462, T8).

A real :class:`Dispatcher` with a registered session and :class:`FakeTmux`: what
is asserted is which CI events reach the session's pane, with what prompt, and
what is recorded for the ones that do not.

Feature: a session is woken by CI only to heal a failing check, and not forever
Requirement: docs/specs/issue-462/requirements.md#R3, #R4
"""

from __future__ import annotations

import time

import pytest

from conftest import FakeTmux, StubInteractiveAdapter
from the_loop import eventlog
from the_loop.control import ControlConfig
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.cimonitor import CiConfig
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent

REF = "github:octo/repo#15"
PR = "github:octo/repo#12"

_counter = iter(range(1, 10_000))


def wait_until(predicate, timeout=5.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture
def events(monkeypatch):
    log = []
    monkeypatch.setattr(
        eventlog, "emit", lambda name, level="info", **f: log.append((name, f))
    )
    return log


@pytest.fixture
def rig(tmp_path):
    def build(ci: CiConfig = CiConfig()):
        tmux = FakeTmux()
        registry = SessionRegistry(tmp_path / "sessions.json")
        registry.register(
            Session(
                work_item=WorkItemRef.parse(REF),
                harness="claude",
                harness_session_id="sess-1",
                cwd=str(tmp_path),
            )
        )
        dispatcher = Dispatcher(
            registry=registry,
            adapters={"claude": StubInteractiveAdapter()},
            config=RoutingConfig(
                registry_dir=str(tmp_path),
                control=ControlConfig(require_start_command=False),
                ci=ci,
            ),
            tmux_runner=tmux,
        )
        return dispatcher, tmux

    built = []

    def make(ci: CiConfig = CiConfig()):
        pair = build(ci)
        built.append(pair[0])
        return pair

    yield make
    for dispatcher in built:
        dispatcher.stop()


def check_run_event(conclusion="failure", sha="a", status="completed", name="test"):
    payload = {
        "action": "completed" if status == "completed" else "created",
        "check_run": {
            "id": 77,
            "name": name,
            "status": status,
            "conclusion": conclusion if status == "completed" else None,
            "head_sha": sha * 40,
            "html_url": "https://github.com/octo/repo/actions/runs/1/job/77",
            "pull_requests": [{"number": 12}],
            "check_suite": {"head_branch": "feature-x"},
            "output": {"title": "1 failed", "summary": "E assert 1 == 2"},
        },
        "repository": {"full_name": "octo/repo"},
    }
    return RoutedEvent(
        event="check_run",
        action=payload["action"],
        delivery_id=f"d-{next(_counter)}",
        work_items=[WorkItemRef.parse(REF), WorkItemRef.parse(PR)],
        payload=payload,
    )


def dropped(events, reason):
    return [
        f
        for name, f in events
        if name == "dispatch.dropped" and f.get("reason") == reason
    ]


def settle(dispatcher, tmux, delivered):
    """Wait for ``delivered`` prompts, and give a stray one the time to show."""
    assert wait_until(lambda: len(tmux.delivers) >= delivered)
    time.sleep(0.05)
    return [prompt for _, prompt in tmux.delivers]


def test_a_failing_check_reaches_the_session_with_the_healing_frame(rig, events):
    """
    Scenario: a failing check run is delivered with the CI section
      Given a live session for the work item a pull request delivers
      When a check run on that pull request completes as a failure
      Then the session receives the event
      And its prompt names the check, the attempt and the pr checks command
      And ci.check_failed is recorded
    """
    dispatcher, tmux = rig()
    dispatcher.handle(check_run_event())
    (prompt,) = settle(dispatcher, tmux, 1)
    assert "CI: a check failed" in prompt
    assert "attempt 1 of 3" in prompt
    assert f"the-loop pr checks {PR} --failing" in prompt
    assert "UNTRUSTED" in prompt  # the template's own framing is still there
    (failed,) = [f for name, f in events if name == "ci.check_failed"]
    assert failed["check"] == "test" and failed["attempt"] == 1
    assert failed["max_attempts"] == 3 and failed["pull_request"] == PR


@pytest.mark.parametrize(
    "event",
    [
        check_run_event("success"),
        check_run_event(status="in_progress"),
        check_run_event("cancelled"),
    ],
    ids=["success", "in-progress", "cancelled"],
)
def test_a_check_that_did_not_fail_is_not_delivered(rig, events, event):
    """
    Scenario: noise does not wake the session
      Given a live session
      When a check run passes, is still running, or was cancelled
      Then nothing reaches the session
      And the drop is recorded as ci-not-actionable
    """
    dispatcher, tmux = rig()
    dispatcher.handle(event)
    assert settle(dispatcher, tmux, 0) == []
    assert len(dropped(events, "ci-not-actionable")) == 1
    assert dispatcher.delivery_outcome(event.delivery_id) == "ci-not-actionable"


@pytest.mark.parametrize("name", ["workflow_run", "check_suite"])
def test_an_aggregate_is_not_delivered(rig, events, name):
    dispatcher, tmux = rig()
    payload = {
        "action": "completed",
        name: {
            "conclusion": "failure",
            "head_sha": "a" * 40,
            "pull_requests": [{"number": 12}],
        },
        "repository": {"full_name": "octo/repo"},
    }
    dispatcher.handle(
        RoutedEvent(
            event=name,
            action="completed",
            delivery_id=f"agg-{name}",
            work_items=[WorkItemRef.parse(REF), WorkItemRef.parse(PR)],
            payload=payload,
        )
    )
    assert settle(dispatcher, tmux, 0) == []
    assert len(dropped(events, "ci-not-actionable")) == 1


def test_attempts_are_bounded_and_end_in_one_escalation(rig, events):
    """
    Scenario: a check the agent cannot fix reaches a person
      Given maxAttempts is 3
      When the same check fails on five different commits
      Then the first three are delivered as attempts 1, 2 and 3
      And the fourth is delivered once as "stop and escalate"
      And the fifth is not delivered and is recorded as ci-autofix-exhausted
    """
    dispatcher, tmux = rig()
    for sha in "abcde":
        dispatcher.handle(check_run_event(sha=sha))
    prompts = settle(dispatcher, tmux, 4)
    assert len(prompts) == 4
    for attempt, prompt in zip((1, 2, 3), prompts):
        assert f"attempt {attempt} of 3" in prompt
    assert "stop and escalate" in prompts[3]
    assert len(dropped(events, "ci-autofix-exhausted")) == 1
    assert [name for name, _ in events].count("ci.autofix_exhausted") == 1


def test_a_pass_resets_the_attempts(rig, events):
    dispatcher, tmux = rig(CiConfig(max_attempts=1))
    dispatcher.handle(check_run_event(sha="a"))
    dispatcher.handle(check_run_event("success", sha="b"))
    dispatcher.handle(check_run_event(sha="c"))
    prompts = settle(dispatcher, tmux, 2)
    assert len(prompts) == 2
    assert "attempt 1 of 1" in prompts[0] and "attempt 1 of 1" in prompts[1]


def test_with_autofix_off_every_ci_event_is_delivered_as_before(rig, events):
    """
    Scenario: the operator turns the gate off
      Given routing.ci.autofix is false
      When a passing and a failing check run arrive
      Then both reach the session
      And neither prompt carries a CI section
    """
    dispatcher, tmux = rig(CiConfig(autofix=False))
    dispatcher.handle(check_run_event("success"))
    dispatcher.handle(check_run_event(sha="b"))
    prompts = settle(dispatcher, tmux, 2)
    assert len(prompts) == 2
    assert not any("CI: a check" in p for p in prompts)
    assert dropped(events, "ci-not-actionable") == []


def test_a_non_ci_event_is_untouched(rig, events):
    dispatcher, tmux = rig()
    dispatcher.handle(
        RoutedEvent(
            event="issue_comment",
            action="created",
            delivery_id="c-1",
            work_items=[WorkItemRef.parse(REF)],
            payload={
                "action": "created",
                "issue": {"number": 15},
                "comment": {"body": "please look", "user": {"login": "someone"}},
                "repository": {"full_name": "octo/repo"},
            },
        )
    )
    (prompt,) = settle(dispatcher, tmux, 1)
    assert "please look" in prompt and "CI: a check" not in prompt


def test_an_unmatched_ci_event_takes_the_unmatched_path(tmp_path, events):
    """No session matches: the gate never runs, and the spawn policy decides."""
    tmux = FakeTmux()
    dispatcher = Dispatcher(
        registry=SessionRegistry(tmp_path / "sessions.json"),
        adapters={"claude": StubInteractiveAdapter()},
        config=RoutingConfig(registry_dir=str(tmp_path)),
        tmux_runner=tmux,
    )
    try:
        dispatcher.handle(check_run_event())
        time.sleep(0.05)
    finally:
        dispatcher.stop()
    assert tmux.delivers == [] and tmux.spawns == []
    assert dropped(events, "ci-not-actionable") == []
    assert [f.get("reason") for n, f in events if n == "dispatch.dropped"] == [
        "spawn-policy"
    ]
