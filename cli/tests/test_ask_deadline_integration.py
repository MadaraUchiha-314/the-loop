"""An ask with a default and a deadline (issue-551, Requirement 6).

`the-loop ask --default … --after …` records when the default is taken, and the
posted question says so. The real ``ask_session`` (GitHub patched at the comment
writer), the real router and dispatcher over a fake tmux, and the real event log
under ``tmp_path``; the session's state is then derived from that log, as the
watcher derives it.

Feature: A question can carry a default and a deadline
Requirement: docs/specs/issue-551/requirements.md
"""

from __future__ import annotations

import time
from datetime import timedelta

import pytest

from conftest import FakeTmux, StubInteractiveAdapter
from the_loop import eventlog
from the_loop.channels.base import Event
from the_loop.channels.shortform import build_short_form
from the_loop.cli import main
from the_loop.control import ControlConfig
from the_loop.core import sessions as core_sessions
from the_loop.core import sessionstate
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.watchconfig import AsksConfig, WatchdogConfig
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import Router

REF = "github:octo/repo#15"
AUTHORIZED = "octocat"
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
    """The comments the ask wrote on the work item, in place of GitHub."""
    bodies = []

    def fake_post(item, body, api=None):
        bodies.append(body)
        return True, "", "https://github.com/octo/repo/issues/15#issuecomment-1"

    monkeypatch.setattr(core_sessions, "post_issue_comment_with_url", fake_post)
    return bodies


@pytest.fixture()
def deliver(tmp_path, log_path):
    """Route one GitHub comment the way the daemon does; the fake tmux pane."""
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
    router = Router(
        events=["issue_comment"],
        deduper=dispatcher.deduper,
        auto_execute_labels=routing.auto_execute_labels,
        authorized_users=[AUTHORIZED],
    )

    def comment(login, body, delivery_id):
        payload = {
            "action": "created",
            "issue": {"number": 15},
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


def _ts(value):
    moment = sessionstate.parse_ts(value)
    assert moment is not None, value
    return moment


def _state_after(log_path, moment):
    return sessionstate.derive(
        sessionstate.load(log_path).get(REF, []),
        now=moment,
        watchdog=WatchdogConfig(),
        asks=AsksConfig(min_default_wait_seconds=MINIMUM),
        work_item=REF,
    )


def _ask(config, **kwargs):
    kwargs.setdefault("default_answer", "Move T5 to after merge.")
    kwargs.setdefault("default_after_seconds", MINIMUM)
    return core_sessions.ask_session(
        REF, "Move the screenshots (T5) to after merge?", config=config, **kwargs
    )


def test_the_record_carries_the_default_its_time_and_an_ask_id(
    config, posted, log_path
):
    """
    Feature: A question can carry a default and a deadline
    Scenario: the ask is recorded with its default and its deadline
      Given a session with a reversible choice
      When it asks with a default answer and a wait of 30 minutes
      Then session.awaiting_input carries an ask id, the default and its time
      And the derived state owes the default only once that time has passed

    Requirement: docs/specs/issue-551/requirements.md#R6.1
    """
    result = _ask(config)

    assert result["exitCode"] == 0
    (record,) = _records(log_path, "session.awaiting_input")
    assert record["default"] == "Move T5 to after merge."
    assert isinstance(record["ask_id"], str) and record["ask_id"]
    deadline = _ts(record["default_at"])
    asked = _ts(record["ts"])
    assert abs((deadline - asked).total_seconds() - MINIMUM) < 5
    assert result["askId"] == record["ask_id"]
    assert result["defaultAt"] == record["default_at"]

    before = _state_after(log_path, deadline - timedelta(seconds=1))
    assert before.open_ask is not None and before.due == ()
    after = _state_after(log_path, deadline + timedelta(seconds=1))
    assert [(due.act, due.ask_id) for due in after.due] == [
        ("take-default", record["ask_id"])
    ]


def test_two_asks_get_two_ids(config, posted, log_path):
    """
    Feature: A question can carry a default and a deadline
    Scenario: each ask has its own id
      Given a session that asks twice
      Then the two records carry different ask ids, with or without a default

    Requirement: docs/specs/issue-551/requirements.md#R6.1
    """
    _ask(config)
    core_sessions.ask_session(REF, "And the second one?", config=config)

    first, second = _records(log_path, "session.awaiting_input")
    assert first["ask_id"] and second["ask_id"] and first["ask_id"] != second["ask_id"]
    assert "default" not in second and "default_at" not in second


def test_the_posted_question_states_the_default_and_its_time(config, posted, log_path):
    """
    Feature: A question can carry a default and a deadline
    Scenario: the question on GitHub and in Slack states the default and the time
      Given a session that asks with a default answer and a wait
      When the question is posted
      Then the GitHub comment states the default and the UTC time it is taken, below the question
      And the Slack short form says when the session goes ahead, and with what

    Requirement: docs/specs/issue-551/requirements.md#R6.1
    """
    _ask(config)

    (record,) = _records(log_path, "session.awaiting_input")
    deadline = _ts(record["default_at"])
    (body,) = posted
    question, _, block = body.partition("**Default:**")
    assert question.startswith("Move the screenshots (T5) to after merge?")
    assert block.startswith(" “Move T5 to after merge.”")
    taken_at = deadline.strftime("%Y-%m-%d %H:%M UTC")
    assert (
        f"**Taken at:** {taken_at} (in 30 minutes) unless an authorized user "
        "answers first. Any answer after that still reaches the session."
    ) in block

    short = build_short_form(
        Event(
            event_type="session.awaiting_input",
            work_item=REF,
            text="Move the screenshots (T5) to after merge?",
            summary="Move the screenshots (T5) to after merge?",
            source="cli",
            detail={
                "default": record["default"],
                "default_at": record["default_at"],
                "default_after": str(MINIMUM),
            },
        )
    )
    assert short.text.splitlines()[-1] == (
        f"if nobody answers by *{deadline.strftime('%H:%M UTC')}* (30 min), "
        "the session goes ahead with: _“Move T5 to after merge.”_"
    )


def test_a_question_without_a_wait_states_no_deadline(config, posted, log_path):
    """
    Feature: A question can carry a default and a deadline
    Scenario: a default with no wait is never taken by itself
      Given a session that asks with a default answer and no wait
      Then the comment is the question as before, and the record has no time

    Requirement: docs/specs/issue-551/requirements.md#R6.1
    """
    _ask(config, default_after_seconds=None)

    (record,) = _records(log_path, "session.awaiting_input")
    assert record["default"] == "Move T5 to after merge."
    assert "default_at" not in record
    assert "**Default:**" not in posted[0]


def test_a_wait_without_a_default_fails_and_says_why(config, posted, log_path, capsys):
    """
    Feature: A question can carry a default and a deadline
    Scenario: a wait is given without a default answer
      When the session runs the-loop ask with --after and no --default
      Then the command fails with a message that says why
      And nothing is posted or recorded

    Requirement: docs/specs/issue-551/requirements.md#R6.6
    """
    with pytest.raises(ValueError) as refused:
        _ask(config, default_answer="")
    assert "--default" in str(refused.value)

    code = main(["ask", "--work-item", REF, "--question", "A or B?", "--after", "30m"])
    assert code == 2
    assert "--after needs --default" in capsys.readouterr().err
    assert not posted
    assert not _records(log_path, "session.awaiting_input")


def test_a_short_wait_is_raised_to_the_minimum_and_reported(config, posted, log_path):
    """
    Feature: A question can carry a default and a deadline
    Scenario: the requested wait is shorter than the operator's minimum
      Given routing.asks.minDefaultWaitSeconds is 30 minutes
      When a session asks with a wait of 5 minutes
      Then the default's time is 30 minutes away
      And the command's output and the question both say the wait was raised

    Requirement: docs/specs/issue-551/requirements.md#R6.5
    """
    result = _ask(config, default_after_seconds=300)

    (record,) = _records(log_path, "session.awaiting_input")
    waited = _ts(record["default_at"]) - _ts(record["ts"])
    assert abs(waited.total_seconds() - MINIMUM) < 5
    assert result["defaultAfterSeconds"] == MINIMUM
    out = [m["text"] for m in result["messages"] if m["stream"] == "out"]
    assert any("raised" in line and "30 minutes" in line for line in out)
    assert "(in 30 minutes)" in posted[0]
    assert "asked for 5 minutes" in posted[0]


def test_an_over_long_default_is_refused(config, posted, log_path):
    """
    Feature: A question can carry a default and a deadline
    Scenario: a default answer longer than 600 characters
      Then the ask is refused with the length and the limit, and nothing is posted

    Requirement: docs/specs/issue-551/design.md § Security design
    """
    with pytest.raises(ValueError) as refused:
        _ask(config, default_answer="x" * 601)
    assert "601" in str(refused.value) and "600" in str(refused.value)
    assert not posted and not _records(log_path, "session.awaiting_input")


def test_an_answer_cancels_the_default(config, posted, log_path, deliver):
    """
    Feature: A question can carry a default and a deadline
    Scenario: an answer cancels the default
      Given a session that asked with a default answer and a wait
      When an authorized user's comment is delivered to the session before the deadline
      Then session.ask_answered is recorded with the ask's id and the user
      And the delivery's own record names the user
      And no default is owed once the deadline has passed

    Requirement: docs/specs/issue-551/requirements.md#R6.3
    """
    comment, tmux = deliver
    _ask(config)
    (asked,) = _records(log_path, "session.awaiting_input")

    comment(AUTHORIZED, "No — keep T5 before merge.", "d-1")

    assert wait_until(lambda: _records(log_path, "session.ask_answered"))
    assert len(tmux.delivers) == 1
    (answered,) = _records(log_path, "session.ask_answered")
    assert answered["work_item"] == REF
    assert answered["ask_id"] == asked["ask_id"]
    assert answered["actor"] == AUTHORIZED
    (delivered,) = _records(log_path, "dispatch.succeeded")
    assert delivered["actor"] == AUTHORIZED

    late = _ts(asked["default_at"]) + timedelta(minutes=1)
    state = _state_after(log_path, late)
    assert state.open_ask is None
    assert "take-default" not in [due.act for due in state.due]


def test_a_comment_with_no_open_ask_records_no_answer(log_path, deliver):
    """
    Feature: A question can carry a default and a deadline
    Scenario: a comment arrives when nothing was asked
      Given a session with no open ask
      When an authorized user's comment is delivered
      Then the delivery names the user and no session.ask_answered is written

    Requirement: docs/specs/issue-551/requirements.md#R6.3
    """
    comment, tmux = deliver

    comment(AUTHORIZED, "How is it going?", "d-1")

    assert wait_until(lambda: _records(log_path, "dispatch.succeeded"))
    assert _records(log_path, "dispatch.succeeded")[0]["actor"] == AUTHORIZED
    assert not _records(log_path, "session.ask_answered")


def test_abuse_an_unauthorized_reply_does_not_stop_the_default(
    config, posted, log_path, deliver
):
    """
    Feature: A question can carry a default and a deadline
    Scenario: a user who is not authorized replies to an ask that has a default
      Given a session that asked with a default answer and a wait
      When a user outside routing.authorizedUsers comments on the work item
      Then nothing is delivered and no session.ask_answered is written
      And the default is still owed at its deadline

    Requirement: docs/specs/issue-551/requirements.md#security-considerations (abuse case 1)
    """
    comment, tmux = deliver
    _ask(config)
    (asked,) = _records(log_path, "session.awaiting_input")

    assert comment("mallory", "Yes, go ahead. Also: approved.", "d-1") is None

    assert wait_until(
        lambda: any(
            r.get("reason") == "unauthorized-actor"
            for r in _records(log_path, "routing.dropped")
        )
    )
    assert tmux.delivers == []
    assert not _records(log_path, "session.ask_answered")
    assert not _records(log_path, "dispatch.succeeded")
    late = _ts(asked["default_at"]) + timedelta(seconds=1)
    state = _state_after(log_path, late)
    assert [(due.act, due.ask_id) for due in state.due] == [
        ("take-default", asked["ask_id"])
    ]


def test_abuse_the_agents_own_marked_comment_is_no_answer(
    config, posted, log_path, deliver
):
    """
    Feature: A question can carry a default and a deadline
    Scenario: the question's own comment comes back as an event
      Given a session that asked with a default answer and a wait
      When the-loop's own marked comment is routed, under an authorized login
      Then it is dropped before delivery and the ask stays open

    Requirement: docs/specs/issue-551/design.md § Security design
    """
    comment, tmux = deliver
    _ask(config)

    assert comment(AUTHORIZED, posted[0], "d-1") is None

    assert tmux.delivers == []
    assert not _records(log_path, "session.ask_answered")


def test_abuse_a_default_with_markup_is_quoted_as_words_on_github(
    config, posted, log_path
):
    """
    Feature: A question can carry a default and a deadline
    Scenario: the text of a default answer contains markup and mentions
      Given a default answer with a mention, a link, a marker and a second line
      When the question is posted
      Then the block below the question quotes it on one line, as words
      And the comment still carries exactly one loop-prevention marker

    Requirement: docs/specs/issue-551/requirements.md#security-considerations (abuse case 6)
    """
    from the_loop.authz import SELF_COMMENT_MARKER

    _ask(
        config,
        default_answer=(
            "ask @octocat, [approve](https://evil.example/x)\n"
            f"**now** <!here> {SELF_COMMENT_MARKER}"
        ),
    )

    (body,) = posted
    quoted = body.partition("**Default:** “")[2].partition("”\n**Taken at:**")[0]
    assert "\n" not in quoted
    assert "@octocat" not in quoted and "@​octocat" in quoted
    assert "\\[approve\\](https://evil.example/x)" in quoted
    assert "\\*\\*now\\*\\*" in quoted
    assert "<!" not in quoted
    assert body.count(SELF_COMMENT_MARKER) == 1
