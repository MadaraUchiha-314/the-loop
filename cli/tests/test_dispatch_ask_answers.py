"""Which delivered comment closes which open ask (issue-551, Requirement 6).

A session may ask on the work item or on one of its pull requests, and a
same-repository pull request's events reach the work item's own session. The
real ``ask_session`` (GitHub patched at the comment writer), the real router and
dispatcher over a fake tmux, and the real event log under ``tmp_path``.

Feature: A question can carry a default and a deadline
Requirement: docs/specs/issue-551/requirements.md
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from conftest import FakeTmux, StubInteractiveAdapter
from the_loop import eventlog
from the_loop.collaborators import CollaboratorStore
from the_loop.control import ControlConfig
from the_loop.core import sessions as core_sessions
from the_loop.core import sessionstate
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.watchconfig import AsksConfig, WatchdogConfig
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import Router

REF = "github:octo/repo#15"
PR = "github:octo/repo#20"
AUTHORIZED = "octocat"
#: On the work item's roster, and on no allow-list: their comment is input.
COLLABORATOR = "dana"
MINIMUM = 1800


def wait_until(predicate, timeout=5.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture()
def log_path(tmp_path):
    path = tmp_path / "events.jsonl"
    eventlog.configure("test", path=path)
    yield path
    eventlog.reset()


@pytest.fixture()
def config(tmp_path):
    return {
        "state": {"root": str(tmp_path / ".the-loop")},
        "routing": {"asks": {"minDefaultWaitSeconds": MINIMUM}},
    }


@pytest.fixture()
def posted(monkeypatch):
    bodies = []

    def fake_post(item, body, api=None):
        bodies.append(body)
        return True, "", "https://github.com/octo/repo/issues/1#issuecomment-1"

    monkeypatch.setattr(core_sessions, "post_issue_comment_with_url", fake_post)
    return bodies


@pytest.fixture()
def deliver(tmp_path, log_path):
    """Route one comment on the issue or on its pull request, as the daemon does."""
    tmux = FakeTmux()
    registry = SessionRegistry(tmp_path / "sessions")
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(tmp_path),
            tmux_target="loop-github-octo-repo-15",
        )
    )
    registry.link_pull_request(REF, PR)
    routing = RoutingConfig(
        dispatch_timeout_seconds=30,
        spawn_workdir=str(tmp_path),
        portable_dir=str(tmp_path / "portable"),
        control=ControlConfig(require_start_command=False),
        authorized_users=[AUTHORIZED],
        asks=AsksConfig(min_default_wait_seconds=MINIMUM),
    )
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=routing,
        tmux_runner=tmux,
    )
    rosters = CollaboratorStore(tmp_path / "portable")
    rosters.add(REF, login=COLLABORATOR, actor=AUTHORIZED, source="cli")
    router = Router(
        events=["issue_comment"],
        deduper=dispatcher.deduper,
        auto_execute_labels=routing.auto_execute_labels,
        authorized_users=[AUTHORIZED],
        collaborators=rosters,
    )

    def comment(number, body, delivery_id, login=AUTHORIZED):
        issue = {"number": number}
        if number != 15:
            issue["pull_request"] = {"url": "https://api.github.com/pulls/20"}
        payload = {
            "action": "created",
            "issue": issue,
            "repository": {"full_name": "octo/repo"},
            "comment": {"body": body, "user": {"login": login}},
        }
        routed = router.route("issue_comment", payload, delivery_id)
        if routed is not None:
            dispatcher.handle(routed)
        return routed

    try:
        yield comment, tmux
    finally:
        dispatcher.stop()


def _records(log_path, event):
    return [r for r in eventlog.read_events(log_path) if r.get("event") == event]


def _ask(ref, config):
    return core_sessions.ask_session(
        ref,
        "Move the screenshots (T5) to after merge?",
        config=config,
        default_answer="Move T5 to after merge.",
        default_after_seconds=MINIMUM,
    )


def _due_after_deadline(log_path, ref, asked):
    deadline = sessionstate.parse_ts(asked["default_at"])
    assert deadline is not None
    late = deadline + timedelta(minutes=1)
    state = sessionstate.derive(
        sessionstate.load(log_path).get(ref, []),
        now=late,
        watchdog=WatchdogConfig(),
        asks=AsksConfig(min_default_wait_seconds=MINIMUM),
        work_item=ref,
    )
    return [due.act for due in state.due]


def test_an_answer_on_the_pull_request_closes_the_ask_asked_there(
    config, posted, log_path, deliver
):
    """
    Feature: A question can carry a default and a deadline
    Scenario: the session asked on its pull request and is answered there
      Given the session of #15, whose same-repository pull request is #20
      And an ask made with --work-item naming #20, a default and a wait
      When an authorized user comments on pull request #20
      Then session.ask_answered is recorded for #20 with the ask's id
      And no default is owed once the deadline has passed

    Requirement: docs/specs/issue-551/requirements.md#R6.3
    """
    comment, tmux = deliver
    _ask(PR, config)
    (asked,) = _records(log_path, "session.awaiting_input")
    assert asked["work_item"] == PR

    comment(20, "No — keep T5 before merge.", "d-1")

    assert wait_until(lambda: _records(log_path, "session.ask_answered"))
    assert len(tmux.delivers) == 1
    (answered,) = _records(log_path, "session.ask_answered")
    assert answered["work_item"] == PR
    assert answered["ask_id"] == asked["ask_id"]
    assert answered["actor"] == AUTHORIZED
    assert "take-default" not in _due_after_deadline(log_path, PR, asked)


def test_an_answer_on_the_pull_request_closes_the_ask_on_the_work_item(
    config, posted, log_path, deliver
):
    """
    Feature: A question can carry a default and a deadline
    Scenario: the session asked on the work item and is answered on its pull request
      Given an ask made on #15 and another made on its pull request #20
      When an authorized user comments on pull request #20
      Then session.ask_answered is recorded once for each of the two asks
      And neither default is owed once the deadlines have passed

    Requirement: docs/specs/issue-551/requirements.md#R6.3
    """
    comment, tmux = deliver
    _ask(REF, config)
    _ask(PR, config)
    asked = {r["work_item"]: r for r in _records(log_path, "session.awaiting_input")}

    comment(20, "No — keep T5 before merge.", "d-1")

    assert wait_until(lambda: len(_records(log_path, "session.ask_answered")) == 2)
    answered = {r["work_item"]: r for r in _records(log_path, "session.ask_answered")}
    for ref in (REF, PR):
        assert answered[ref]["ask_id"] == asked[ref]["ask_id"]
        assert "take-default" not in _due_after_deadline(log_path, ref, asked[ref])


def test_a_comment_on_the_work_item_leaves_no_answer_where_nothing_was_asked(
    config, posted, log_path, deliver
):
    """
    Feature: A question can carry a default and a deadline
    Scenario: only the work item has an open ask
      When an authorized user comments on the work item
      Then exactly one session.ask_answered is written, for the work item

    Requirement: docs/specs/issue-551/requirements.md#R6.3
    """
    comment, tmux = deliver
    _ask(REF, config)

    comment(15, "No.", "d-1")

    assert wait_until(lambda: _records(log_path, "session.ask_answered"))
    (answered,) = _records(log_path, "session.ask_answered")
    assert answered["work_item"] == REF


def test_abuse_a_collaborators_comment_answers_no_ask_and_resets_no_budget(
    config, posted, log_path, deliver
):
    """
    Feature: A question can carry a default and a deadline
    Scenario: a collaborator, who may add input and answer nothing, comments
      Given a session that was nudged once and then asked with a default
      And a collaborator on the work item who is on no allow-list
      When the collaborator comments on the work item
      Then the comment is delivered to the session as input
      And no session.ask_answered is recorded, and the delivery names no actor
      And the default is still owed at its deadline
      And the nudge already spent stays spent

    Requirement: docs/specs/issue-551/requirements.md#security-considerations
    (abuse cases 1 and 2; fail closed: an answer whose author cannot be shown
    to be authorized)
    """
    comment, tmux = deliver
    eventlog.emit("session.turn_started", work_item=REF, node="build")
    eventlog.emit("session.turn_ended", work_item=REF, node="build", reason="exit-met")
    eventlog.emit("session.nudged", work_item=REF, stall_id=f"{REF}@x", nudge=1)
    _ask(REF, config)
    (asked,) = _records(log_path, "session.awaiting_input")

    routed = comment(15, "Yes, move it.", "d-1", login=COLLABORATOR)

    assert routed is not None, "a collaborator's comment is routed as input"
    assert wait_until(lambda: _records(log_path, "dispatch.succeeded"))
    assert len(tmux.delivers) == 1
    (delivered,) = _records(log_path, "dispatch.succeeded")
    assert not delivered.get("actor")
    assert _records(log_path, "session.ask_answered") == []
    assert "take-default" in _due_after_deadline(log_path, REF, asked)
    state = sessionstate.derive(
        sessionstate.load(log_path).get(REF, []),
        now=datetime.now(timezone.utc),
        watchdog=WatchdogConfig(),
        asks=AsksConfig(min_default_wait_seconds=MINIMUM),
        work_item=REF,
    )
    assert state.nudges_spent == 1
    assert [ask.ask_id for ask in state.open_asks] == [asked["ask_id"]]

    # The same words from an authorized user do all three.
    comment(15, "Yes, move it.", "d-2")
    assert wait_until(lambda: _records(log_path, "session.ask_answered"))
    assert "take-default" not in _due_after_deadline(log_path, REF, asked)
