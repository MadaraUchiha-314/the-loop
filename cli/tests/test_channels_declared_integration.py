"""A work item's declared collaboration channel, end to end (issue-375).

The real :class:`SlackBotChannel` and the real inbound pipeline against the fake
Slack client every other channel test uses, with real declarations in a real
portable record on a tmp path. What is asserted is the pair of behaviours the
declaration buys — the conversation moves to the room, and the room's messages
are about the work item — plus the two things that must **not** happen: a
kickoff in a declared room, and a message in somebody else's room reaching this
work item.

Spec: docs/specs/issue-375/testing-plan.md T5–T11.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import _state_with_stores
from the_loop.channels import inbound
from the_loop.channels.base import Event
from the_loop.channels.slack import (
    DEFAULT_BOT_TOKEN_ENV,
    SlackBotChannel,
    SlackChannelConfig,
)
from the_loop.workchannels import CollaborationChannelStore
from test_channels import FakeSlackClient, cli_config

REF = "github:octo/repo#375"
OTHER = "github:octo/repo#376"
CENTRAL = "C123"
ROOM = "C0TMP375"


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")


def _portable(config):
    return CollaborationChannelStore(Path(config["state"]["root"]) / "portable")


def declare(config, work_item=REF, target=ROOM):
    _portable(config).add(work_item, f"slack@{target}", actor="octocat", source="cli")


def channel_for(config, client):
    return SlackBotChannel(
        SlackChannelConfig.from_mapping(config),
        Path(config["state"]["root"]) / "channels" / "slack.json",
        client_factory=lambda token: client,
    )


def state_of(config):
    return _state_with_stores(Path(config["state"]["root"]) / "channels" / "slack.json")


def conversation(config, work_item=REF):
    """The binding as the bot reads it — asserted present, so the type is not
    Optional at every call site below."""
    record = state_of(config).conversation(work_item)
    assert record is not None, f"no conversation for {work_item}"
    return record


class Sink:
    """The three injection seams the pipeline already has, recorded.

    Nothing is monkeypatched: ``post_comment``, ``deliver`` and ``create_issue``
    are the parameters ``handle_socket_event`` and ``poll_once`` take, so what is
    exercised here is the production path with its own boundaries stubbed.
    """

    def __init__(self):
        self.recorded: list = []
        self.delivered: list = []
        self.created: list = []

    def post_comment(self, item, body, **kwargs):
        self.recorded.append((getattr(item, "ref", str(item)), body))
        return True, ""

    def deliver(self, ref, text, actor="", comment=True, config=None):
        self.delivered.append((ref, text))
        return {"delivered": True}

    def create_issue(self, repo, title, body, labels=(), gh_binary="gh"):
        self.created.append((repo, title))
        return True, "", "github:octo/repo#999", "https://x/999"

    @property
    def refs(self):
        return [ref for ref, _ in self.delivered]


def socket(config, event, sink, client=None):
    return inbound.handle_socket_event(
        event,
        config,
        post_comment=sink.post_comment,
        deliver=sink.deliver,
        create_issue=sink.create_issue,
        client_factory=lambda token: client or FakeSlackClient(),
    )


# -- outbound: the conversation lives in the declared room (T5, T6) -------------


def test_the_thread_root_is_opened_in_the_declared_channel(tmp_path):
    """
    Feature: a work item's updates go to the room it was declared into
      Scenario: the first update on a declared work item
        Given #375 has declared slack@C0TMP375
        When the-loop posts that work item's first event
        Then the thread root is opened in C0TMP375, not in the central channel,
             and the binding records that room

    Requirement: docs/specs/issue-375/requirements.md R2.1
    """
    config = cli_config(tmp_path)
    declare(config)
    client = FakeSlackClient()
    bot = channel_for(config, client)

    bot.post(Event(event_type="comment.human", work_item=REF, text="hello"))

    assert [post["channel"] for post in client.posted] == [ROOM, ROOM]  # root + reply
    assert conversation(config)["channel"] == ROOM


def test_without_a_declaration_the_central_channel_is_unchanged(tmp_path):
    """R2.3: a work item that declared nothing behaves exactly as before."""
    config = cli_config(tmp_path)
    client = FakeSlackClient()
    channel_for(config, client).post(
        Event(event_type="comment.human", work_item=REF, text="hello")
    )
    assert [post["channel"] for post in client.posted] == [CENTRAL, CENTRAL]
    assert conversation(config)["channel"] == CENTRAL


def test_a_declaration_after_the_conversation_started_moves_it(tmp_path):
    """
    Feature: a work item's updates go to the room it was declared into
      Scenario: the room is declared after the conversation began
        Given #375's conversation is already a thread in the central channel
        When slack@C0TMP375 is declared and the next event is posted
        Then a root is opened in C0TMP375, the binding follows it, the record
             says the move was a declaration, and the old thread is told where
             the conversation went — because replies there reach nobody now

    Requirement: docs/specs/issue-375/requirements.md R1.8, R2.2
    """
    config = cli_config(tmp_path)
    client = FakeSlackClient()
    bot = channel_for(config, client)
    bot.post(Event(event_type="comment.human", work_item=REF, text="first"))
    old_thread = conversation(config)["thread"]

    declare(config)
    bot.post(Event(event_type="comment.human", work_item=REF, text="second"))

    record = conversation(config)
    assert record["channel"] == ROOM
    assert record["origin"] == "declared"
    pointer = [
        post
        for post in client.posted
        if post["channel"] == CENTRAL and post["thread_ts"] == old_thread
    ]
    assert any("has moved" in post["text"] for post in pointer)
    # …and the reply itself went to the new room, in the new thread.
    assert client.posted[-1]["channel"] == ROOM
    # One work item, one conversation (issue-312): the old thread is unmapped,
    # which is exactly what the pointer message above exists to say out loud.
    assert state_of(config).work_item_for(old_thread) is None


def test_open_uses_the_declared_room_too(tmp_path):
    """R2.1: the spawn path's `open` resolves the same home `post` does."""
    config = cli_config(tmp_path)
    declare(config)
    client = FakeSlackClient()
    channel_for(config, client).open(REF)
    assert [post["channel"] for post in client.posted] == [ROOM]


# -- inbound, Socket Mode: every message in the room is about the item (T7, T8) --


def _message(text, *, channel=ROOM, ts="1700.000100", thread="", user="UHUMAN"):
    event = {"ts": ts, "channel": channel, "user": user, "text": text}
    if thread:
        event["thread_ts"] = thread
    return event


def test_a_top_level_message_in_the_room_is_a_reply_on_the_work_item(tmp_path):
    """
    Feature: a declared room has one subject
      Scenario: a member types at the top level of the room
        Given #375 has declared slack@C0TMP375
        When an authorized member posts a top-level message there
        Then it is recorded on #375 and delivered to its session — and no new
             work item is opened

    Requirement: docs/specs/issue-375/requirements.md R3.1
    """
    config = cli_config(tmp_path, publish=["work-item.reply", "work-item.create"])
    declare(config)
    sink = Sink()

    outcome = socket(config, _message("what is the retry budget?"), sink)

    assert outcome["outcome"] == "processed"
    assert outcome["event"] == "work-item.reply"
    assert [ref for ref, _ in sink.recorded] == [REF]
    assert sink.refs == [REF]
    assert sink.created == []


def test_a_message_in_an_unbound_thread_in_the_room_reaches_the_work_item(tmp_path):
    """R3.2: a dedicated room has one subject, threads in it included."""
    config = cli_config(tmp_path)
    declare(config)
    sink = Sink()

    outcome = socket(
        config,
        _message("in a thread nobody bound", ts="1700.000200", thread="1700.000100"),
        sink,
    )

    assert outcome["outcome"] == "processed"
    assert sink.refs == [REF]


def test_the_central_channel_still_opens_work_items(tmp_path):
    """R3.1: nothing changes in a channel nobody declared."""
    config = cli_config(tmp_path, publish=["work-item.create", "work-item.reply"])
    config["channels"]["slack"]["kickoff"] = {"repo": "octo/repo", "labels": []}
    declare(config)
    sink = Sink()

    socket(config, _message("look at the retry budget", channel=CENTRAL), sink)

    assert sink.created  # the kickoff path, untouched


def test_declaring_the_central_channel_stops_it_opening_work_items(tmp_path):
    """
    Feature: a declared room has one subject
      Scenario: the operator's own channel is declared on a work item
        Given #375 declared the central channel itself
        When a member types a top-level message there
        Then it is a message on #375 and NOT a new issue

    Requirement: docs/specs/issue-375/requirements.md R3.1
    """
    config = cli_config(tmp_path, publish=["work-item.create", "work-item.reply"])
    config["channels"]["slack"]["kickoff"] = {"repo": "octo/repo", "labels": []}
    declare(config, target=CENTRAL)
    sink = Sink()

    socket(config, _message("still about 375", channel=CENTRAL), sink)

    assert sink.created == []
    assert sink.refs == [REF]


def test_a_bound_thread_wins_over_the_room(tmp_path):
    """
    Feature: a declared room has one subject
      Scenario: another work item's thread is in the declared room
        Given #376's conversation is a thread inside #375's declared room
        When a member replies in that thread
        Then the reply reaches #376 — the binding is more specific than the room

    Requirement: docs/specs/issue-375/requirements.md R3.3
    """
    config = cli_config(tmp_path)
    declare(config)
    client = FakeSlackClient()
    channel_for(config, client).bind("1700.000900", OTHER, ROOM, origin="kickoff")
    sink = Sink()

    socket(
        config,
        _message("about 376", ts="1700.000901", thread="1700.000900"),
        sink,
        client,
    )

    assert sink.refs == [OTHER]


def test_an_unauthorized_member_in_the_room_is_still_dropped(tmp_path):
    """R3.5: the declaration moves a conversation; it grants nobody anything."""
    config = cli_config(tmp_path)
    declare(config)
    sink = Sink()

    outcome = socket(config, _message("let me in", user="UINTRUDER"), sink)

    assert outcome["outcome"] == "unauthorized-actor"
    assert sink.recorded == [] and sink.delivered == []


def test_a_message_in_an_undeclared_room_is_unmapped(tmp_path):
    """R3.1: only a DECLARED room attributes its messages."""
    config = cli_config(tmp_path)
    sink = Sink()
    outcome = socket(config, _message("hello?"), sink)
    assert outcome["outcome"] == "unmapped"
    assert sink.recorded == [] and sink.delivered == []


def test_an_undeclared_room_goes_quiet_again(tmp_path):
    """R1.6: removing the declaration takes effect on the next event."""
    config = cli_config(tmp_path)
    declare(config)
    _portable(config).remove(REF, f"slack@{ROOM}")
    sink = Sink()
    assert socket(config, _message("still here?"), sink)["outcome"] == "unmapped"


# -- inbound, poll mode (T9, T10) ------------------------------------------------


def poll(config, sink, client):
    return inbound.poll_once(
        config,
        client_factory=lambda token: client,
        post_comment=sink.post_comment,
        deliver=sink.deliver,
        create_issue=sink.create_issue,
    )


def test_the_poll_read_baselines_a_room_before_delivering_anything(tmp_path):
    """
    Feature: a declared room has one subject
      Scenario: a room with history is declared
        Given slack@C0TMP375 has a month of messages and no cursor
        When the poll transport reads it for the first time
        Then nothing is delivered and the room is baselined at its newest ts

    Requirement: docs/specs/issue-375/requirements.md R3.6
    """
    config = cli_config(tmp_path)
    declare(config)
    client = FakeSlackClient()
    client.history = [
        {"ts": "1600.000001", "user": "UHUMAN", "text": "old"},
        {"ts": "1600.000002", "user": "UHUMAN", "text": "older still"},
    ]
    sink = Sink()

    assert poll(config, sink, client)["replies"] == 0
    assert sink.delivered == []

    client.history = [{"ts": "1700.000003", "user": "UHUMAN", "text": "new"}]
    assert poll(config, sink, client)["processed"] == 1
    assert sink.refs == [REF]


def test_the_poll_read_processes_a_room_message_once(tmp_path):
    """R3.6: the room's cursor advances, so a second cycle re-reads nothing."""
    config = cli_config(tmp_path)
    declare(config)
    client = FakeSlackClient()
    client.history = [{"ts": "1600.000001", "user": "UHUMAN", "text": "baseline"}]
    sink = Sink()
    poll(config, sink, client)

    client.history = [{"ts": "1700.000004", "user": "UHUMAN", "text": "once"}]
    poll(config, sink, client)
    poll(config, sink, client)

    assert sink.refs == [REF]


def test_the_poll_read_ignores_a_room_nobody_declared(tmp_path):
    """R3.1: with no declaration there is no room to read — and no kickoff
    either, because this deployment granted none."""
    config = cli_config(tmp_path)
    client = FakeSlackClient()
    client.history = [{"ts": "1700.000005", "user": "UHUMAN", "text": "hello"}]
    sink = Sink()
    assert poll(config, sink, client)["replies"] == 0
    assert sink.delivered == []
