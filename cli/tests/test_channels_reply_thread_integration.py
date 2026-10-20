"""The agent answers a Slack mention in the thread it came from (issue-507).

The real :class:`SlackBotChannel` and the real inbound pipeline against the fake
Slack client, with a real declaration in a real portable record on a tmp path —
the same harness as ``test_channels_declared_integration.py``. A mention in a
thread of the work item's room is delivered; the agent's next ``comment.agent``
must be a reply in that thread, and the next event that starts a conversation
ends it.

Spec: docs/specs/issue-507/testing-plan.md T2–T4.
"""

from __future__ import annotations

import pytest

from the_loop.channels import inbound
from the_loop.channels.base import Event
from the_loop.channels.slack import DEFAULT_BOT_TOKEN_ENV
from the_loop.channels.state import ChannelState
from test_channels import FakeSlackClient, cli_config
from test_channels_declared_integration import (
    REF,
    ROOM,
    Sink,
    _message,
    channel_for,
    declare,
    socket,
    state_of,
)

THREAD = "1700.000100"
OTHER_THREAD = "1700.000300"


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")


def _room(tmp_path, **slack):
    """A work item with a declared room whose conversation is already open, so
    every post below is one message and ``client.posted[-1]`` is the event."""
    config = cli_config(tmp_path, **slack)
    declare(config)
    client = FakeSlackClient()
    bot = channel_for(config, client)
    assert bot.open(REF).ok
    return config, client, bot


def _mention_in(config, client, thread, ts):
    outcome = socket(
        config,
        _message("<@UBOT> what is the retry budget?", ts=ts, thread=thread),
        Sink(),
        client=client,
    )
    assert outcome["outcome"] == "processed"
    return outcome


def _answer(bot, text="three retries"):
    return bot.post(Event(event_type="comment.agent", work_item=REF, text=text))


def test_the_answer_to_a_thread_mention_is_a_reply_in_that_thread(tmp_path):
    """
    Feature: the agent answers where it was asked
      Scenario: a collaborator mentions the-loop inside a thread of the room
        Given #375 has declared slack@C0TMP375 as its room
        And someone started a thread in the room
        When an authorized member mentions the-loop in that thread
        And the agent then comments on the work item
        Then the comment is posted as a reply in that thread
        And the post result names that thread

    Requirement: docs/specs/issue-507/bugfix.md R1.1, R1.2, R1.4, R3.3
    """
    config, client, bot = _room(tmp_path)
    _mention_in(config, client, THREAD, "1700.000200")

    result = _answer(bot)

    assert (client.posted[-1]["channel"], client.posted[-1]["thread_ts"]) == (
        ROOM,
        THREAD,
    )
    assert result.thread == THREAD


def test_every_answer_stays_in_the_thread_until_something_else_happens(tmp_path):
    """R1.3: the reply thread holds for every agent comment, not just one."""
    config, client, bot = _room(tmp_path)
    _mention_in(config, client, THREAD, "1700.000200")

    _answer(bot, "first")
    _answer(bot, "second")

    assert [p["thread_ts"] for p in client.posted[-2:]] == [THREAD, THREAD]


def test_a_mention_in_another_thread_moves_the_answer_there(tmp_path):
    """R2.1: the newest in-thread mention wins."""
    config, client, bot = _room(tmp_path)
    _mention_in(config, client, THREAD, "1700.000200")
    _mention_in(config, client, OTHER_THREAD, "1700.000400")

    _answer(bot)

    assert client.posted[-1]["thread_ts"] == OTHER_THREAD


def test_a_top_level_mention_is_answered_at_the_top_level(tmp_path):
    """
    Feature: the agent answers where it was asked
      Scenario: after a thread mention, someone mentions the-loop at the top level
        Given a mention in a room thread set the reply thread
        When an authorized member mentions the-loop at the top level of the room
        And the agent then comments
        Then the comment is a top-level message, as before issue-507

    Requirement: docs/specs/issue-507/bugfix.md R2.2
    """
    config, client, bot = _room(tmp_path)
    _mention_in(config, client, THREAD, "1700.000200")
    _mention_in(config, client, "", "1700.000500")

    _answer(bot)

    assert client.posted[-1]["thread_ts"] is None


def test_a_phase_change_ends_the_reply_thread(tmp_path):
    """
    Feature: the agent answers where it was asked
      Scenario: the work item moves to a new phase after a thread mention
        Given a mention in a room thread set the reply thread
        When the room hears the next phase start
        Then that announcement is a top-level message
        And the agent's next comment is top-level too

    Requirement: docs/specs/issue-507/bugfix.md R2.3
    """
    config, client, bot = _room(tmp_path, room={"style": "classic"})
    _mention_in(config, client, THREAD, "1700.000200")

    bot.post(Event(event_type="phase.started", work_item=REF, text="design"))
    started = client.posted[-1]
    _answer(bot)

    assert started["thread_ts"] is None
    assert client.posted[-1]["thread_ts"] is None


def test_a_gate_prompt_ends_the_reply_thread(tmp_path):
    """R2.3: a gate starts a conversation of its own, at the top level."""
    config, client, bot = _room(tmp_path)
    _mention_in(config, client, THREAD, "1700.000200")

    bot.post(
        Event(
            event_type="phase-approval-pending",
            work_item=REF,
            text="design is ready for review",
            detail={"node": "design-approval"},
        )
    )
    gate = client.posted[-1]
    _answer(bot)

    assert gate["thread_ts"] is None
    assert client.posted[-1]["thread_ts"] is None


def test_progress_does_not_end_the_reply_thread(tmp_path):
    """R2.3: a within-phase progress event is not a new conversation."""
    config, client, bot = _room(tmp_path)
    _mention_in(config, client, THREAD, "1700.000200")

    bot.post(
        Event(
            event_type="phase.progress",
            work_item=REF,
            text="critic review",
            detail={"phase": "needs-review", "node": "critic-review"},
        )
    )
    _answer(bot)

    assert client.posted[-1]["thread_ts"] == THREAD


def test_room_policy_still_drops_what_it_drops(tmp_path):
    """R1.5: the session-started cheat-sheet never reaches a room, thread or not."""
    config, client, bot = _room(tmp_path)
    _mention_in(config, client, THREAD, "1700.000200")
    before = len(client.posted)

    bot.post(
        Event(
            event_type="comment.agent",
            work_item=REF,
            text="the-loop started an interactive session for #375\n"
            "tmux attach -t loop-375",
        )
    )

    assert len(client.posted) == before


def test_without_a_mention_the_answer_is_top_level_as_before(tmp_path):
    """R2.4: nothing changes for a room nobody addressed from a thread."""
    _, client, bot = _room(tmp_path)

    _answer(bot)

    assert client.posted[-1]["thread_ts"] is None


def test_abuse_an_unauthorized_thread_mention_sets_no_reply_thread(tmp_path):
    """
    Feature: only an authorized speaker steers the answer
      Scenario: a stranger mentions the-loop in a room thread
        Given #375 has declared a room
        When a member who is not authorized mentions the-loop in a thread there
        Then the message is refused as before
        And the agent's next comment is still a top-level message

    Requirement: docs/specs/issue-507/bugfix.md abuse case 1
    """
    config, client, bot = _room(tmp_path)

    outcome = socket(
        config,
        _message("<@UBOT> hi", ts="1700.000200", thread=THREAD, user="UINTRUDER"),
        Sink(),
        client=client,
    )
    _answer(bot)

    assert outcome["outcome"] == "unauthorized-actor"
    assert state_of(config).delivery_for(REF)["replyThread"] == ""
    assert client.posted[-1]["thread_ts"] is None


def test_abuse_a_reply_thread_in_another_channel_is_ignored(tmp_path):
    """Abuse case 2, R3.2: a reply thread never moves a post to another channel."""
    config, client, bot = _room(tmp_path)
    path = bot.state_path
    with ChannelState.locked(path, bot.stores) as state:
        state.remember_delivery(REF, replyChannel="C0ELSEWHERE", replyThread=THREAD)
        state.save(path)

    _answer(bot)

    assert (client.posted[-1]["channel"], client.posted[-1]["thread_ts"]) == (
        ROOM,
        None,
    )


def test_save_fails_the_reply_is_still_delivered_and_posts_top_level(
    tmp_path, monkeypatch
):
    """R3.1: noting the thread is best-effort; the reply and the post stand."""
    config, client, bot = _room(tmp_path)
    sink = Sink()
    real_save = ChannelState.save

    def flaky_save(self, path):
        if self.delivery.get(REF, {}).get("replyThread"):
            raise OSError("disk full")
        return real_save(self, path)

    monkeypatch.setattr(ChannelState, "save", flaky_save)
    outcome = inbound.handle_socket_event(
        _message("<@UBOT> hi", ts="1700.000200", thread=THREAD),
        config,
        post_comment=sink.post_comment,
        deliver=sink.deliver,
        create_issue=sink.create_issue,
        client_factory=lambda token: client,
        addressed=True,
    )
    monkeypatch.setattr(ChannelState, "save", real_save)
    _answer(bot)

    assert outcome["outcome"] == "processed"
    assert sink.refs == [REF]
    assert client.posted[-1]["thread_ts"] is None


def test_a_mention_that_is_not_delivered_keeps_the_earlier_thread(tmp_path):
    """Critic C1: a mention whose delivery fails does not steal the answer the
    agent is writing to an earlier, delivered question."""
    config, client, bot = _room(tmp_path)
    _mention_in(config, client, THREAD, "1700.000200")

    def refuse(ref, text, **kwargs):
        raise LookupError("no live session")

    sink = Sink()
    inbound.handle_socket_event(
        _message("<@UBOT> and this?", ts="1700.000400", thread=OTHER_THREAD),
        config,
        post_comment=sink.post_comment,
        deliver=refuse,
        create_issue=sink.create_issue,
        client_factory=lambda token: client,
        addressed=True,
    )
    _answer(bot)

    assert client.posted[-1]["thread_ts"] == THREAD
