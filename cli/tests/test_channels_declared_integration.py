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
from the_loop.channels.base import ChannelError, Event
from the_loop.channels.slack import (
    DEFAULT_BOT_TOKEN_ENV,
    SlackBotChannel,
    SlackChannelConfig,
)
from the_loop.workchannels import CollaborationChannelStore
from test_channels import FakeSlackClient, cli_config

REF = "github:octo/repo#375"
OTHER = "github:octo/repo#376"
CENTRAL = "D123"
ROOM = "C0TMP375"


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")


def _portable(config):
    return CollaborationChannelStore(Path(config["state"]["root"]) / "portable")


def declare(config, work_item=REF, target=ROOM, listen="mentions"):
    _portable(config).add(
        work_item, f"slack@{target}", actor="octocat", source="cli", listen=listen
    )


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


def socket(config, event, sink, client=None, addressed=True):
    """A room is mention-gated (issue-389 R1.1): every event these tests send
    is a member addressing the-loop, delivered as `app_mention`, unless a test
    says otherwise."""
    return inbound.handle_socket_event(
        event,
        config,
        post_comment=sink.post_comment,
        deliver=sink.deliver,
        create_issue=sink.create_issue,
        client_factory=lambda token: client or FakeSlackClient(),
        addressed=addressed,
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

    # A plain message in the bot's DM: the DM keeps `message.im` as input.
    socket(
        config,
        _message("look at the retry budget", channel=CENTRAL),
        sink,
        addressed=False,
    )

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

    socket(config, _message("still about 375", channel=CENTRAL), sink, addressed=False)

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
    declare(config, listen="all")  # a poll read hears only an `all` room (issue-389)
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
    declare(config, listen="all")  # a poll read hears only an `all` room (issue-389)
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


# -- names, not ids (PR #376 review) ---------------------------------------------


def _with_directory(config, names):
    """Seed the directory cache so a name resolves with no Slack call at all."""
    import json
    import time

    path = Path(config["state"]["root"]) / "local" / "slack-directory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"conversations": {"names": dict(names), "fetchedAt": time.time()}})
    )


def test_the_central_channel_may_be_declared_by_name(tmp_path):
    """
    Feature: an operator names the room, not its id
      Scenario: channels.slack.channel is `#the-loop`
        Given the workspace has #the-loop as C123
        When a work item's first event is posted
        Then the root lands in C123 — the name resolved once, and every
             outbound path read the same id

    Requirement: docs/specs/issue-375/requirements.md R5.1
    """
    config = cli_config(tmp_path, channel="#the-loop")
    _with_directory(config, {"the-loop": CENTRAL})
    client = FakeSlackClient()

    channel_for(config, client).post(
        Event(event_type="comment.human", work_item=REF, text="hello")
    )

    assert [post["channel"] for post in client.posted] == [CENTRAL, CENTRAL]
    assert conversation(config)["channel"] == CENTRAL


def test_a_central_channel_name_that_resolves_to_nothing_refuses(tmp_path):
    """R5.3: an unresolvable name is not a silent fallback to nothing — the post
    raises, and the message says what to check."""
    config = cli_config(tmp_path, channel="#gone")
    _with_directory(config, {})
    client = FakeSlackClient()

    with pytest.raises(ChannelError, match="resolves to no channel"):
        channel_for(config, client).post(
            Event(event_type="comment.human", work_item=REF, text="hello")
        )
    assert client.posted == []


def test_an_id_still_needs_no_directory_at_all(tmp_path):
    """R6.2: the pre-existing configuration keeps working with no cache, no
    scope and no lookup."""
    config = cli_config(tmp_path)  # channel="C123", an id
    client = FakeSlackClient()
    channel_for(config, client).post(
        Event(event_type="comment.human", work_item=REF, text="hello")
    )
    assert [post["channel"] for post in client.posted] == [CENTRAL, CENTRAL]


def test_an_allow_list_handle_authorizes_its_member(tmp_path):
    """
    Feature: an operator names the person, not their member id
      Scenario: routing.authorizedUsers names @dana
        Given the allow-list carries the handle `dana` rather than U0DANA
        When U0DANA posts in a declared room
        Then the message is processed — the handle resolved to that id

    Requirement: docs/specs/issue-375/requirements.md R5.2
    """
    import json
    import time

    config = cli_config(tmp_path, authorized=("dana",))
    declare(config)
    path = Path(config["state"]["root"]) / "local" / "slack-directory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"users": {"names": {"dana": "U0DANA"}, "fetchedAt": time.time()}})
    )
    sink = Sink()

    outcome = socket(config, _message("hello", user="U0DANA"), sink)

    assert outcome["outcome"] == "processed"
    assert sink.refs == [REF]


def test_an_unresolvable_handle_authorizes_nobody(tmp_path):
    """R5.3: fail closed — an entry that cannot be resolved contributes no id,
    so the failure direction is fewer people, never more."""
    config = cli_config(tmp_path, authorized=("ghost",))
    declare(config)
    _with_directory(config, {})
    sink = Sink()

    outcome = socket(config, _message("hello", user="U0DANA"), sink)

    assert outcome["outcome"] == "unauthorized-actor"
    assert sink.delivered == []


# -- issue-378: a declared room is the conversation (T11, T12, T13, T15) ---------


def test_a_declared_room_is_the_conversation_and_events_are_top_level(tmp_path):
    """
    Feature: a declared room is channel-based
      Scenario: the first event on a work item declared into a room
        Given #375 has declared slack@C0TMP375 and has no conversation yet
        When the-loop posts that work item's first event
        Then one top-level message opens the room as the conversation
        And the event is a top-level message in the room, not a reply
        And the record carries no thread and `mode: channel`

    Requirement: docs/specs/issue-378/requirements.md R5.1, R5.2
    """
    config = cli_config(tmp_path)
    declare(config)
    client = FakeSlackClient()
    bot = channel_for(config, client)

    result = bot.post(Event(event_type="comment.human", work_item=REF, text="hello"))

    assert [(p["channel"], p["thread_ts"]) for p in client.posted] == [
        (ROOM, None),
        (ROOM, None),
    ]
    assert "posted in this channel" in client.posted[0]["text"]
    record = conversation(config)
    assert record["channel"] == ROOM
    assert record["thread"] == ""
    assert record["mode"] == "channel"
    assert result.ok
    state = state_of(config)
    assert state.thread_for(REF) is None
    assert state.conversation_for(REF) == (ROOM, "")


def test_a_room_conversation_is_opened_once_and_every_event_is_top_level(tmp_path):
    """R5.2, R5.7: `open` is idempotent; the second event opens nothing.

    Pinned to the classic room style: this asserts the room *plumbing* invariant
    (top-level, never threaded), which the issue-393 rework's collapse rules
    (agentic default) deliberately change — those have their own tests below.
    """
    config = cli_config(tmp_path, room={"style": "classic"})
    declare(config)
    client = FakeSlackClient()
    bot = channel_for(config, client)

    assert bot.open(REF).ok
    assert bot.open(REF).ok
    bot.post(Event(event_type="phase.started", work_item=REF, text="started"))
    bot.post(Event(event_type="phase.completed", work_item=REF, text="done"))

    assert [(p["channel"], p["thread_ts"]) for p in client.posted] == [
        (ROOM, None),
        (ROOM, None),
        (ROOM, None),
    ]
    assert conversation(config)["origin"] == "start"


def test_an_agentic_room_collapses_an_intermediate_transition(tmp_path):
    """issue-393 B5/R6.1: in the default agentic room, an intermediate
    `phase.completed` is collapsed — RoomPolicy drops it — so it is not a third
    top-level message. The `phase.started` still posts."""
    config = cli_config(tmp_path)  # agentic is the default
    declare(config)
    client = FakeSlackClient()
    bot = channel_for(config, client)

    assert bot.open(REF).ok
    bot.post(
        Event(
            event_type="phase.started",
            work_item=REF,
            text="🔨 Starting design.",
            detail={"node": "design"},
        )
    )
    bot.post(
        Event(
            event_type="phase.completed",
            work_item=REF,
            text="done",
            detail={"node": "design"},
        )
    )
    # The started message posted; the completed one was collapsed (not a
    # separate post). Exactly one posted message mentions the phase, and none
    # carries the collapsed "done".
    import json

    with_phase = [p for p in client.posted if "Starting design." in json.dumps(p)]
    assert len(with_phase) == 1
    assert "done" not in [p.get("text") for p in client.posted]


def test_a_thread_declared_into_a_room_moves_to_the_room_as_a_room(tmp_path):
    """R5.4: the room opens as a conversation, the old thread is told and unmapped."""
    config = cli_config(tmp_path)
    client = FakeSlackClient()
    bot = channel_for(config, client)
    bot.post(Event(event_type="comment.human", work_item=REF, text="first"))
    old_thread = conversation(config)["thread"]

    declare(config)
    bot.post(Event(event_type="comment.human", work_item=REF, text="second"))

    record = conversation(config)
    assert (record["channel"], record["thread"], record["mode"], record["origin"]) == (
        ROOM,
        "",
        "channel",
        "declared",
    )
    pointer = [p for p in client.posted if p["thread_ts"] == old_thread]
    assert any("has moved" in p["text"] for p in pointer)
    assert (
        client.posted[-1]["channel"] == ROOM and client.posted[-1]["thread_ts"] is None
    )
    assert state_of(config).work_item_for(old_thread) is None


def test_a_thread_already_bound_inside_the_room_keeps_its_shape(tmp_path):
    """R5.5: a conversation opened as a thread in the room (before this change)
    stays a thread — a restart never changes the shape of what exists."""
    config = cli_config(tmp_path)
    declare(config)
    client = FakeSlackClient()
    bot = channel_for(config, client)
    bot.bind("1700.000042", REF, ROOM, origin="event")

    bot.post(Event(event_type="comment.human", work_item=REF, text="hello"))

    assert [(p["channel"], p["thread_ts"]) for p in client.posted] == [
        (ROOM, "1700.000042")
    ]
    assert conversation(config)["thread"] == "1700.000042"


def test_a_reply_under_a_room_message_reaches_the_work_item(tmp_path):
    """R5.6, A8: a thread under one of the-loop's room messages is the item's."""
    config = cli_config(tmp_path)
    declare(config)
    client = FakeSlackClient()
    bot = channel_for(config, client)
    bot.post(Event(event_type="phase.started", work_item=REF, text="started"))
    room_message = client.posted[-1]
    sink = Sink()

    outcome = socket(
        config,
        _message(
            "a reply under the-loop's message", ts="1700.000900", thread="1700.000002"
        ),
        sink,
        client=client,
    )

    assert room_message["thread_ts"] is None
    assert outcome["outcome"] == "processed"
    assert sink.refs == [REF]
