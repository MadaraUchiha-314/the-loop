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

    def create_issue(self, repo, title, body, labels=(), api=None):
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
    # issue-549 R10: the `phase.*` pair is bookkeeping, so two ordinary events
    bot.post(Event(event_type="comment.human", work_item=REF, text="started"))
    bot.post(Event(event_type="work-item.closed", work_item=REF, text="done"))

    assert [(p["channel"], p["thread_ts"]) for p in client.posted] == [
        (ROOM, None),
        (ROOM, None),
        (ROOM, None),
    ]
    assert conversation(config)["origin"] == "start"


def test_an_agentic_room_collapses_an_intermediate_transition(tmp_path):
    """issue-393 B5/R6.1, as issue-549 R10.1 tightens it: the `phase.*` pair is
    bookkeeping, so neither the `phase.completed` nor the `phase.started` is a
    message in the room."""
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
    # Neither half of the transition reached the room: only its opening is there.
    import json

    with_phase = [p for p in client.posted if "Starting design." in json.dumps(p)]
    assert with_phase == []
    assert "done" not in [p.get("text") for p in client.posted]
    assert len(client.posted) == 1


def test_an_agentic_room_edits_a_phase_in_place_on_progress(tmp_path):
    """issue-393 R6.3: a `phase.progress` within a phase edits that phase's one
    room message in place (chat.update) rather than posting a new one — so a long
    phase (the review chain) shows where it is instead of going silent."""
    config = cli_config(tmp_path)  # agentic
    declare(config)
    client = FakeSlackClient()
    bot = channel_for(config, client)
    assert bot.open(REF).ok

    # The phase's first progress posts and is remembered…
    bot.post(
        Event(
            event_type="phase.progress",
            work_item=REF,
            text="🔨 needs-review reached self-review.",
            detail={"phase": "needs-review", "node": "self-review"},
        )
    )
    # …a later progress in the same phase edits it, not a second message.
    bot.post(
        Event(
            event_type="phase.progress",
            work_item=REF,
            text="🔨 needs-review reached critic-review.",
            detail={"phase": "needs-review", "node": "critic-review"},
        )
    )
    assert len(client.updates) == 1  # the second progress was an edit
    channel, ts, text, _blocks = client.updates[0]
    assert "critic-review" in text


def test_the_session_voice_wins_over_a_later_template_for_the_same_node(tmp_path):
    """issue-393 B9/R12.3: when the session speaks for a node (its question, a
    source=cli event), a later runtime template (phase.started) for that same
    node is dropped — the agent's own words win over the boilerplate."""
    config = cli_config(tmp_path)  # agentic
    declare(config)
    client = FakeSlackClient()
    bot = channel_for(config, client)
    assert bot.open(REF).ok

    # The session asks — its own words, source=cli, recorded as spoken-for.
    bot.post(
        Event(
            event_type="session.awaiting_input",
            work_item=REF,
            text="🤔 Two small calls — per-line or per-file?",
            detail={"node": "requirements-definition"},
            source="cli",
        )
    )
    # A runtime template for the same node now — it should be suppressed.
    bot.post(
        Event(
            event_type="phase.started",
            work_item=REF,
            text="the-loop: started requirements-definition",
            detail={"node": "requirements-definition"},
        )
    )
    import json

    posts = json.dumps(client.posted)
    assert "per-line or per-file" in posts  # the session's message landed
    # the template did not add a second message for that node
    template_posts = [
        p for p in client.posted if "started requirements-definition" in json.dumps(p)
    ]
    assert template_posts == []


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


# -- issue-549: the short form, the long form, and where each goes (task 9) ------

LONG_COMMENT = """## Design ready

The Slack channel plans each delivery as a short message plus its long form.

| Where | Top level | Thread |
|---|---|---|
| room | short form | long form |
| central | short form | none |

- [x] placement
- [ ] status reactions

Approve the design?"""

SUMMARY = "Design is drafted. Approve it, or ask for changes?"


def _comment(text=LONG_COMMENT, summary=SUMMARY):
    return Event(
        event_type="comment.agent",
        work_item=REF,
        text=text,
        url="https://github.com/octo/repo/issues/375#issuecomment-1",
        source="cli",
        summary=summary,
        event_id="ev-549-1",
    )


def _markdown(post):
    blocks = post["blocks"] or []
    return [block for block in blocks if block.get("type") == "markdown"]


def test_a_long_comment_in_a_declared_room_posts_a_short_message_and_its_long_form_in_the_thread(
    tmp_path,
):
    """
    Feature: every Slack message is a short form, and in a room its long form
      Scenario: a long comment in a declared room posts a short message and its long form in the thread
        Given #375 has declared slack@C0TMP375
        When the-loop posts the agent's comment carrying a summary, a table and a
             task list
        Then the summary is a top-level message in the room, its text fallback is
             that same short form, and it carries the Open on GitHub button
        And the whole comment, table and task list as written, is one markdown
             block in that message's thread
        And no message asks Slack for a link preview

    Requirement: docs/specs/issue-549/requirements.md R4.1, R2.1, R2.2, R2.6, R2.7,
                 R3.2, R5
    """
    config = cli_config(tmp_path)
    declare(config)
    client = FakeSlackClient()

    channel_for(config, client).post(_comment())

    opening, short, part = client.posted
    assert opening["channel"] == short["channel"] == part["channel"] == ROOM
    assert short["thread_ts"] is None  # top-level in the room (R4.1)
    assert short["blocks"][0]["text"]["text"] == SUMMARY
    assert short["text"] == SUMMARY  # the fallback is the short form (R2.7)
    assert short["blocks"][-1]["elements"][0]["url"].endswith("#issuecomment-1")
    assert not _markdown(short)
    short_ts = "1700.000002"
    assert part["thread_ts"] == short_ts  # in the short message's thread
    (block,) = _markdown(part)
    assert block["text"] == LONG_COMMENT  # every word, as written (R1.1, R2.2)
    assert part["text"] == SUMMARY
    for extra in client.unfurls:
        assert extra == {"unfurl_links": False, "unfurl_media": False}


def test_the_central_channel_gets_the_short_form_only(tmp_path):
    """
    Feature: every Slack message is a short form, and in a room its long form
      Scenario: the central channel gets the short form only
        Given #375 declared no room, so its conversation is a thread in the
             central channel
        When the-loop posts the agent's long comment with a summary
        Then the summary is a reply in the work item's thread, with the Open on
             GitHub button
        And no long form is posted anywhere in the central channel

    Requirement: docs/specs/issue-549/requirements.md R4.2, R3.2
    """
    config = cli_config(tmp_path)
    client = FakeSlackClient()

    channel_for(config, client).post(_comment())

    root, short = client.posted
    assert root["channel"] == short["channel"] == CENTRAL
    assert short["thread_ts"] == "1700.000001"  # the item's thread
    assert short["text"] == SUMMARY
    assert [block["type"] for block in short["blocks"]] == ["section", "actions"]
    button = short["blocks"][-1]["elements"][0]
    assert button["url"].endswith("#issuecomment-1")
    assert not any(_markdown(post) for post in client.posted)
    record = state_of(config).posted_for(REF, "ev-549-1")
    assert record == {"channel": CENTRAL, "top": "1700.000002", "parts": []}


def test_the_loop_comment_with_a_summary_posts_the_summary_to_slack_and_the_whole_text_to_github(
    tmp_path, monkeypatch
):
    """
    Feature: every Slack message is a short form, and in a room its long form
      Scenario: the-loop comment with a summary posts the summary to Slack and the whole text to GitHub
        Given #375 has declared slack@C0TMP375, subscribed to the agent's comments
        When the session runs `the-loop comment` with a body and a `--summary`
        Then the GitHub comment is the whole body, without the summary
        And the room's top-level message is the summary
        And the whole body is the long form in that message's thread

    Requirement: docs/specs/issue-549/requirements.md R3.1, R3.2, R3.8, R4.1
    """
    from ghfakes import FakeGitHubClient
    from the_loop.core import github_ops

    config = cli_config(tmp_path, subscribe=["comment.agent"])
    declare(config)
    client = FakeSlackClient()
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)
    github = FakeGitHubClient()

    result = github_ops.comment(
        REF, LONG_COMMENT, config, client=github, summary=SUMMARY
    )

    assert result["posted"] is True and result["channelsPosted"] == 1
    (posted,) = github.posted
    body = posted[3]
    assert LONG_COMMENT in body and SUMMARY not in body  # R3.8
    _opening, short, part = client.posted
    assert short["thread_ts"] is None and short["text"] == SUMMARY
    assert part["thread_ts"] == "1700.000002"
    (block,) = _markdown(part)
    assert block["text"] == LONG_COMMENT


# -- issue-549 task 11: progress edits edit one message, long form included -------


def _progress(event_id, text, summary="Review is under way.", node="self-review"):
    return Event(
        event_type="phase.progress",
        work_item=REF,
        text=text,
        summary=summary,
        detail={"phase": "needs-review", "node": node},
        event_id=event_id,
    )


def _paragraphs(count, size=5000):
    return "\n\n".join(f"Paragraph {n}. " + "word " * (size // 5) for n in range(count))


def test_a_progress_edit_in_the_central_channel_edits_one_message(tmp_path):
    """
    Feature: progress within a phase edits one message
      Scenario: a progress edit in the central channel edits one message
        Given #375 declared no room, so its conversation is a thread in the
             central channel
        When two progress events for the same phase are delivered
        Then the first is one reply in the work item's thread
        And the second edits that reply in place, posting nothing new

    Requirement: docs/specs/issue-549/requirements.md R6.1
    """
    config = cli_config(tmp_path)
    client = FakeSlackClient()
    bot = channel_for(config, client)

    bot.post(_progress("ev-p1", "self-review is running.", summary=""))
    posted = len(client.posted)
    bot.post(
        _progress(
            "ev-p2", "critic-review is running.", summary="", node="critic-review"
        )
    )

    assert len(client.posted) == posted  # root + the one progress reply
    root, first = client.posted
    assert first["channel"] == CENTRAL and first["thread_ts"] == "1700.000001"
    ((channel, ts, text, _blocks),) = client.updates
    assert (channel, ts) == (CENTRAL, "1700.000002")
    assert "critic-review" in text


def test_a_progress_edit_with_fewer_parts_deletes_the_surplus(tmp_path):
    """
    Feature: progress within a phase edits one message
      Scenario: a progress edit with fewer parts deletes the surplus
        Given #375 has declared slack@C0TMP375
        And its phase's progress message holds a long form of three parts
        When a progress event for the same phase carries a one-part long form
        Then the progress message is edited in place
        And its first long-form reply is edited to the new long form
        And the two surplus replies are deleted
        And nothing is posted

    Requirement: docs/specs/issue-549/requirements.md R6.1, R6.2
    """
    config = cli_config(tmp_path)
    declare(config)
    client = FakeSlackClient()
    bot = channel_for(config, client)

    bot.post(_progress("ev-p1", _paragraphs(6)))
    opening, short, *parts = client.posted
    assert len(parts) == 3
    assert all(part["thread_ts"] == "1700.000002" for part in parts)
    before = len(client.posted)

    bot.post(
        _progress(
            "ev-p2", "The review chain reached critic-review.", node="critic-review"
        )
    )

    assert len(client.posted) == before  # no second copy (R6.2)
    edited = [ts for _channel, ts, _text, _blocks in client.updates]
    assert edited == ["1700.000002", "1700.000003"]
    _, _, _, blocks = client.updates[1]
    assert _markdown({"blocks": blocks})[0]["text"] == (
        "The review chain reached critic-review."
    )
    assert client.deleted == [(ROOM, "1700.000004"), (ROOM, "1700.000005")]
    record = state_of(config).posted_for(REF, "ev-p2")
    assert record == {"channel": ROOM, "top": "1700.000002", "parts": ["1700.000003"]}


# -- issue-549 R11: Approve from Slack at every human gate ----------------------

REGISTERED = "github:Octo/Repo#549"  # the work item's own spelling
LOWERED = "github:octo/repo#549"  # what the runtime published on #549
GATE_NODE = "design-approval"
INTERACTIVE = {
    "publish": ["work-item.reply", "gate.feedback"],
    "read": {"mode": "socket"},
    "subscribe": ["phase-approval-pending"],
}


class PressClient(FakeSlackClient):
    """The recording client, plus the ephemeral a refused press is told by."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.ephemeral = []  # (channel, user, text, thread)

    def chat_postEphemeral(self, *, channel, user, text, thread_ts=None):
        self.ephemeral.append((channel, user, text, thread_ts))
        return {"ok": True}


def _notify(config, work_item, tmp_path, node=GATE_NODE):
    """The graph's own `notify` hook opening ``node`` for ``work_item`` — the
    path that published #549's gates under a lowercased ref."""
    from the_loop.graph import hooks  # noqa: F401 — registers the hooks
    from the_loop.graph.contract import HookContext, WorkItem
    from the_loop.graph.hooks.sideeffects import notify

    spec = tmp_path / "spec"
    spec.mkdir(exist_ok=True)
    return notify(
        HookContext(
            work_item=WorkItem(ref=work_item, id="issue-549", spec_dir=spec),
            node={"id": node},
            boundary="entry",
            repo=tmp_path,
            config=config,
            params={"event": "phase-approval-pending"},
        )
    )


def _gate_buttons(post):
    (block,) = [b for b in post["blocks"] or [] if b.get("type") == "actions"]
    return block.get("block_id"), [e.get("action_id") for e in block["elements"]]


def _gate_press(
    *,
    channel=ROOM,
    ts="1700.000002",
    thread="",
    user="UHUMAN",
    node=GATE_NODE,
    action="the-loop:approve",
    value="approved",
):
    message = {"ts": ts, **({"thread_ts": thread} if thread else {})}
    action_payload = {"action_id": action, "value": value}
    if node:
        action_payload["block_id"] = f"the-loop:gate:{node}"
    return {
        "type": "block_actions",
        "user": {"id": user},
        "channel": {"id": channel},
        "message": message,
        "container": {
            "message_ts": ts,
            "channel_id": channel,
            **({"thread_ts": thread} if thread else {}),
        },
        "actions": [action_payload],
        "action_ts": "1900.1",
    }


def _press(config, payload, sink, client):
    return inbound.handle_socket_action(
        payload,
        config,
        post_comment=sink.post_comment,
        deliver=sink.deliver,
        client_factory=lambda token: client,
    )


@pytest.fixture()
def gate_open(monkeypatch):
    """The graph parked at ``design-approval`` — the read the pipeline makes."""
    monkeypatch.setattr(inbound, "_gate_read", lambda ref, cfg: (True, GATE_NODE))


def test_a_gate_opened_under_a_lowercased_ref_posts_its_buttons_in_the_work_items_own_thread(
    tmp_path, monkeypatch, gate_open
):
    """
    Feature: approve from Slack at every human gate
      Scenario: a gate opened under a lowercased ref posts its buttons in the work item's own thread
        Given #549's conversation is a thread in the central channel, bound
             under its registered spelling github:Octo/Repo#549
        And the channel can receive a press
        When the graph's notify hook opens design-approval under
             github:octo/repo#549
        Then the gate message is a reply in that same thread, with Approve and
             Request changes naming the gate
        And no second thread is opened
        And a press on it reaches the work item and counts as its answer

    Requirement: docs/specs/issue-549/requirements.md R11.1, R11.2
    """
    config = cli_config(tmp_path, **INTERACTIVE)
    client = PressClient()
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)
    channel_for(config, client).open(REGISTERED)

    result = _notify(config, LOWERED, tmp_path)

    assert result.status == "pass", result
    root, gate = client.posted  # no second root
    assert root["thread_ts"] is None
    assert gate["channel"] == CENTRAL and gate["thread_ts"] == "1700.000001"
    block_id, actions = _gate_buttons(gate)
    assert block_id == f"the-loop:gate:{GATE_NODE}"
    assert {"the-loop:approve", "the-loop:changes"} <= set(actions)
    state = state_of(config)
    assert state.delivery_for(REGISTERED)["gateTs"] == {GATE_NODE: "1700.000002"}
    assert state.conversation_for(LOWERED) == state.conversation_for(REGISTERED)

    sink = Sink()
    outcome = _press(
        config,
        _gate_press(channel=CENTRAL, ts="1700.000002", thread="1700.000001"),
        sink,
        client,
    )
    assert outcome["outcome"] == "processed" and outcome["event"] == "gate.feedback"
    assert [ref for ref, _ in sink.recorded] == [REGISTERED]


def test_a_press_in_a_declared_room_approves_the_gate(tmp_path, gate_open):
    """
    Feature: approve from Slack at every human gate
      Scenario: a press in a declared room approves the gate
        Given #375 has declared slack@C0TMP375 and the channel can receive a press
        And design-approval's message is a top-level message in the room
        When an authorized member presses Approve on it
        Then the press is resolved to #375 through the room
        And it is recorded on the ticket as the same gate answer a typed
             "approved" is, which the gate classifies as approved
        And the pressed message is edited to acknowledge it, its buttons gone

    Requirement: docs/specs/issue-549/requirements.md R11.4
    """
    from the_loop.graph.contract import HookContext, WorkItem
    from the_loop.graph.hooks.feedback import classify_feedback

    config = cli_config(tmp_path, **INTERACTIVE)
    declare(config)
    client = PressClient()
    channel_for(config, client).post(
        Event(
            event_type="phase-approval-pending",
            work_item=REF,
            text="design.md is ready for its gate.",
            url="https://github.com/octo/repo/issues/375",
            detail={"node": GATE_NODE},
            source="loop",
            event_id="ev-gate-375",
        )
    )
    gate = client.posted[-1]
    assert gate["channel"] == ROOM and gate["thread_ts"] is None
    sink = Sink()

    outcome = _press(config, _gate_press(ts="1700.000002"), sink, client)

    assert outcome["outcome"] == "processed" and outcome["event"] == "gate.feedback"
    ((ref, body),) = sink.recorded
    assert ref == REF and "approved" in body

    def verdict(text):
        spec = tmp_path / "spec"
        spec.mkdir(exist_ok=True)
        return classify_feedback(
            HookContext(
                work_item=WorkItem(ref=REF, id="issue-375", spec_dir=spec),
                node={"id": GATE_NODE},
                boundary="exit",
                repo=tmp_path,
                config={"authorizedUsers": ["gh-UHUMAN"]},
                event={"comments": [{"author": "gh-UHUMAN", "body": text}]},
            )
        ).outcome

    assert verdict(body) == verdict("approved") == "approved"  # R11.4
    ((channel, ts, _text, blocks),) = client.updates
    assert (channel, ts) == (ROOM, "1700.000002")
    assert "the-loop:approve" not in str(blocks)


def test_a_channel_that_cannot_receive_a_press_shows_how_to_approve_on_github(
    tmp_path,
):
    """
    Feature: approve from Slack at every human gate
      Scenario: a channel that cannot receive a press shows how to approve on GitHub
        Given a channel read by polling, so no press can reach the-loop
        When a gate opens for #375
        Then its message carries no Approve or Request changes button
        And one line says how to answer the gate on GitHub, linked

    Requirement: docs/specs/issue-549/requirements.md R11.5
    """
    config = cli_config(
        tmp_path,
        publish=["work-item.reply", "gate.feedback"],
        subscribe=["phase-approval-pending"],
    )
    client = PressClient()

    channel_for(config, client).post(
        Event(
            event_type="pr-review-pending",
            work_item=REF,
            text="PR #12 is ready for review.",
            url="https://github.com/octo/repo/pull/12",
            detail={"node": "human-approval"},
            source="loop",
        )
    )

    gate = client.posted[-1]
    assert "the-loop:approve" not in str(gate["blocks"])
    assert "the-loop:changes" not in str(gate["blocks"])
    lines = [
        element["text"]
        for block in gate["blocks"]
        if block["type"] == "context"
        for element in block["elements"]
    ]
    (line,) = [text for text in lines if "on GitHub" in text]
    assert "<https://github.com/octo/repo/pull/12|on GitHub>" in line
    assert "approved" in line


def test_every_approval_gate_is_remembered_with_its_buttons(tmp_path):
    """R11.1: the security sign-off is a gate like the others — its message is
    remembered, so it can be answered and closed."""
    config = cli_config(tmp_path, **INTERACTIVE)
    declare(config)
    client = PressClient()
    bot = channel_for(config, client)
    for event_type, node in (
        ("phase-approval-pending", "requirements-approval"),
        ("pr-review-pending", "human-approval"),
        ("security-sign-off-pending", "security-sign-off"),
    ):
        bot.post(
            Event(
                event_type=event_type,
                work_item=REF,
                text=f"{node} is open.",
                detail={"node": node},
                source="loop",
            )
        )
        block_id, actions = _gate_buttons(client.posted[-1])
        assert block_id == f"the-loop:gate:{node}"
        assert "the-loop:approve" in actions
    assert set(state_of(config).delivery_for(REF)["gateTs"]) == {
        "requirements-approval",
        "human-approval",
        "security-sign-off",
    }


# -- abuse cases 7 and 8 (T8) ----------------------------------------------------


def test_unauthorized_press_refused(tmp_path, gate_open):
    """Abuse case 7: a press from a member not on the allow-list is not counted —
    nothing is recorded or delivered, the message is not edited, only the
    presser is told, and the drop is recorded."""
    from the_loop import eventlog

    config = cli_config(tmp_path, **INTERACTIVE)
    declare(config)
    client = PressClient()
    channel_for(config, client).post(
        Event(
            event_type="phase-approval-pending",
            work_item=REF,
            text="design.md is ready.",
            detail={"node": GATE_NODE},
            source="loop",
        )
    )
    sink = Sink()
    log = tmp_path / "events.jsonl"
    eventlog.configure("test", path=log, enabled=True)
    try:
        outcome = _press(
            config, _gate_press(ts="1700.000002", user="USTRANGER"), sink, client
        )
    finally:
        eventlog.configure("test", enabled=False)

    assert outcome == {"outcome": "unauthorized-actor"}
    assert sink.recorded == [] and sink.delivered == []
    assert client.updates == [] and client.acks == []
    ((channel, user, text, _thread),) = client.ephemeral
    assert (channel, user) == (ROOM, "USTRANGER")
    assert "not counted" in text
    assert '"reason":"unauthorized-actor"' in log.read_text(encoding="utf-8")


def test_stale_press_changes_nothing(tmp_path, monkeypatch):
    """Abuse case 8: a press on a gate that is not open — answered, so its
    message is no longer the open one; a forged node; or a graph parked
    elsewhere — records nothing, edits nothing, and only the presser is told."""
    config = cli_config(tmp_path, **INTERACTIVE)
    declare(config)
    client = PressClient()
    channel_for(config, client).post(
        Event(
            event_type="phase-approval-pending",
            work_item=REF,
            text="design.md is ready.",
            detail={"node": GATE_NODE},
            source="loop",
        )
    )
    sink = Sink()
    monkeypatch.setattr(inbound, "_gate_read", lambda ref, cfg: (True, GATE_NODE))
    cases = [
        # a forged node: no message of it is open
        _gate_press(ts="1700.000002", node="requirements-approval"),
        # a message that is not the gate's open one (an older, answered copy)
        _gate_press(ts="1700.000001"),
    ]
    for payload in cases:
        assert _press(config, payload, sink, client) == {"outcome": "gate-not-open"}
    # the graph has moved on to another gate
    monkeypatch.setattr(
        inbound, "_gate_read", lambda ref, cfg: (True, "tasks-approval")
    )
    assert _press(config, _gate_press(ts="1700.000002"), sink, client) == {
        "outcome": "gate-not-open"
    }
    # the graph is parked at no gate at all
    monkeypatch.setattr(inbound, "_gate_read", lambda ref, cfg: (False, ""))
    assert _press(config, _gate_press(ts="1700.000002"), sink, client) == {
        "outcome": "gate-not-open"
    }

    assert sink.recorded == [] and sink.delivered == []
    assert client.updates == [] and client.acks == []
    assert len(client.ephemeral) == 4
    assert {user for _c, user, _t, _th in client.ephemeral} == {"UHUMAN"}
    assert all("no longer open" in text for _c, _u, text, _th in client.ephemeral)


GATE_GRAPH = {
    "start": "draft",
    "nodes": [
        {"id": "draft"},
        {
            "id": GATE_NODE,
            "actor": "human",
            "session": "inherit",
            "entry": [{"hook": "notify", "with": {"event": "phase-approval-pending"}}],
            "exit": ["classify-feedback"],
        },
        {"id": "done", "terminal": True},
    ],
    "edges": [
        {"from": "draft", "to": GATE_NODE, "on": "pass"},
        {"from": GATE_NODE, "to": "done", "on": "approved"},
        {"from": GATE_NODE, "to": "draft", "on": "changes-requested"},
    ],
}


def test_a_gate_answered_on_github_edits_its_slack_message_to_show_the_outcome(
    tmp_path, monkeypatch
):
    """
    Feature: approve from Slack at every human gate
      Scenario: a gate answered on GitHub edits its Slack message to show the outcome
        Given #375 has declared slack@C0TMP375 and the channel can receive a press
        And the runtime opened design-approval, whose message has its buttons
        When an authorized user answers "approved" on GitHub and the runtime
             takes the gate's edge
        Then the gate's message is edited, not reposted, to show the outcome
             and who answered
        And its buttons are gone, its link kept, and the gate is no longer
             remembered as open, so a later press on it changes nothing

    Requirement: docs/specs/issue-549/requirements.md R11.6
    """
    from the_loop.graph import hooks  # noqa: F401 — registers the hooks
    from the_loop.graph.model import compile_graph
    from the_loop.graph.runtime import Runtime

    config = {
        **cli_config(tmp_path, **INTERACTIVE),
        "authorizedUsers": ["owner"],
    }
    declare(config)
    client = PressClient()
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)
    repo = tmp_path / "repo"
    (repo / "docs" / "specs" / "issue-375").mkdir(parents=True)
    runtime = Runtime(repo, graph=compile_graph(GATE_GRAPH), config=config)

    runtime.advance("issue-375", ref=REF)
    gate = client.posted[-1]
    assert "the-loop:approve" in str(gate["blocks"])
    gate_ts = state_of(config).delivery_for(REF)["gateTs"][GATE_NODE]
    posted = len(client.posted)

    report = runtime.advance(
        "issue-375",
        ref=REF,
        event={"comments": [{"author": "owner", "body": "approved"}]},
    )

    assert report.outcome == "approved"
    assert len(client.posted) == posted  # an edit, never a new message
    ((channel, ts, text, blocks),) = client.updates
    assert (channel, ts) == (ROOM, gate_ts)
    assert "approved" in text and "owner" in text and GATE_NODE in text
    assert "the-loop:approve" not in str(blocks)
    assert "the-loop:changes" not in str(blocks)
    assert "the-loop:open" in str(blocks)  # the link stays
    assert GATE_NODE not in state_of(config).delivery_for(REF)["gateTs"]

    monkeypatch.setattr(inbound, "_gate_read", lambda ref, cfg: (True, GATE_NODE))
    sink = Sink()
    assert _press(config, _gate_press(ts=gate_ts), sink, client) == {
        "outcome": "gate-not-open"
    }
    assert sink.recorded == []
