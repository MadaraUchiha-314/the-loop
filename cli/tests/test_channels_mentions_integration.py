"""The mention is the address, and three acts each end in the session — end to
end through the socket handler, the pipeline, the fake Slack client and the fake
ledger writer (issue-389). Spec: docs/specs/issue-389/testing-plan.md T2.

Feature: a Slack conversation reaches the-loop only when addressed
Requirement: docs/specs/issue-389/requirements.md#R1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import _state_with_stores
from the_loop.authz import is_self_authored
from the_loop.channels import inbound, once
from the_loop.channels.envelope import parse as parse_envelope
from the_loop.channels.slack import (
    DEFAULT_BOT_TOKEN_ENV,
    SlackBotChannel,
    SlackChannelConfig,
)
from the_loop.collaborators import CollaboratorStore
from the_loop.workchannels import CollaborationChannelStore
from test_channels import FakeSlackClient, cli_config

REF = "github:octo/repo#389"
ROOM = "C0TMP389"
CENTRAL = "C123"
DM = "D0BOT"
BOT = "UBOT"
GRANTS = [
    "work-item.reply",
    "control.command",
    "work-item.create",
    "context.added",
    "decision.recorded",
]


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")


@pytest.fixture(autouse=True)
def _fresh_ring():
    """The once-ring is process-wide; each test starts with an empty one."""
    once.reset()
    yield
    once.reset()


class Client(FakeSlackClient):
    """The fake, plus what this work item's paths call: an ephemeral post, a
    permalink, and `auth.test` with the workspace URL."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.ephemeral = []  # (channel, user, text)

    def chat_postEphemeral(self, *, channel, user, text):
        self.ephemeral.append((channel, user, text))
        return {"ok": True}

    def chat_getPermalink(self, *, channel, message_ts):
        return {
            "ok": True,
            "permalink": f"https://x.slack.com/archives/{channel}/p{message_ts.replace('.', '')}",
        }

    def auth_test(self):
        return {"ok": True, "user_id": BOT, "url": "https://x.slack.com/"}


class Sink:
    def __init__(self):
        self.recorded: list = []
        self.delivered: list = []
        self.created: list = []

    def post_comment(self, item, body, **kwargs):
        self.recorded.append((getattr(item, "ref", str(item)), body))
        n = len(self.recorded)
        return True, "", f"https://github.com/octo/repo/issues/389#issuecomment-{n}"

    def deliver(self, ref, text, actor="", comment=True, config=None, **extra):
        self.delivered.append({"ref": ref, "text": text, "actor": actor, **extra})
        return {"delivered": True}

    def create_issue(self, repo, title, body, labels=(), gh_binary="gh"):
        self.created.append((repo, title))
        return True, "", "github:octo/repo#999", "https://x/999"


def envelope_of(body):
    """The record's envelope, asserted present so the type is not Optional."""
    envelope = parse_envelope(body)
    assert envelope is not None, "no envelope in the record"
    return envelope


def config_for(tmp_path, channel=CENTRAL, **slack):
    publish = slack.pop("publish", GRANTS)
    cfg = cli_config(tmp_path, channel=channel, publish=publish, **slack)
    cfg["channels"]["slack"]["read"] = {"mode": "socket"}
    return cfg


def portable(config):
    return Path(config["state"]["root"]) / "portable"


def declare(config, target=ROOM, listen="mentions", work_item=REF):
    CollaborationChannelStore(portable(config)).add(
        work_item, f"slack@{target}", actor="octocat", source="cli", listen=listen
    )


def bot_for(config, client):
    return SlackBotChannel(
        SlackChannelConfig.from_mapping(config),
        Path(config["state"]["root"]) / "channels" / "slack.json",
        client_factory=lambda token: client,
    )


def send(
    config,
    sink,
    client,
    *,
    addressed,
    channel=ROOM,
    text,
    ts="1900.5",
    thread="",
    user="UHUMAN",
):
    event = {"ts": ts, "channel": channel, "user": user, "text": text}
    if thread:
        event["thread_ts"] = thread
    return inbound.handle_socket_event(
        event,
        config,
        post_comment=sink.post_comment,
        deliver=sink.deliver,
        create_issue=sink.create_issue,
        client_factory=lambda token: client,
        addressed=addressed,
    )


# -- R1: the address ---------------------------------------------------------------


def test_a_message_without_the_mention_leaves_no_trace(tmp_path):
    """
    Scenario: a message without the mention leaves no trace
      Given #389 declared the room C0TMP389 (listen: mentions)
      When an authorized member posts a plain message there
      Then it is dropped as not-addressed
      And nothing is recorded, delivered or reacted to, and no cursor moves
    """
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), Client()
    outcome = send(config, sink, client, addressed=False, text="talking to bob")
    assert outcome == {"outcome": "not-addressed"}
    assert sink.recorded == [] and sink.delivered == [] and client.reactions == []
    state = _state_with_stores(
        Path(config["state"]["root"]) / "channels" / "slack.json"
    )
    assert state.cursors == {}


def test_a_mention_in_a_mentions_room_is_input(tmp_path):
    """
    Scenario: a mention in a mentions room is input
      Given #389 declared the room C0TMP389
      When an authorized member posts "<@UBOT> what is blocking you?" there
      Then the message, without the bot's token, is mirrored onto the ticket
      And delivered into the session as a reply
    """
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), Client()
    outcome = send(
        config, sink, client, addressed=True, text=f"<@{BOT}> what is blocking you?"
    )
    assert outcome["outcome"] == "processed" and outcome["event"] == "work-item.reply"
    assert sink.delivered[0]["ref"] == REF
    assert sink.delivered[0]["text"] == "what is blocking you?"
    assert "what is blocking you?" in sink.recorded[0][1]
    assert client.reactions and client.reactions[-1][2] == "white_check_mark"


def test_a_mention_under_the_loops_own_question_is_input_and_a_plain_reply_is_not(
    tmp_path,
):
    """
    Scenario: a mention under the-loop's own question is input and a plain reply there is not
      Given the-loop opened #389's thread in the central channel
      When a member replies "<@UBOT> use A" in it
      Then it is input
      When another member replies "use B" in it without the mention
      Then it is dropped as not-addressed — one rule, no exemption for the-loop's threads
    """
    config = config_for(tmp_path)
    sink, client = Sink(), Client()
    bot = bot_for(config, client)
    bot.bind("1800.1", REF, CENTRAL, origin="start")
    mentioned = send(
        config,
        sink,
        client,
        addressed=True,
        channel=CENTRAL,
        text=f"<@{BOT}> use A",
        thread="1800.1",
        ts="1800.2",
    )
    plain = send(
        config,
        sink,
        client,
        addressed=False,
        channel=CENTRAL,
        text="use B",
        thread="1800.1",
        ts="1800.3",
    )
    assert mentioned["outcome"] == "processed"
    assert plain == {"outcome": "not-addressed"}
    assert [d["text"] for d in sink.delivered] == ["use A"]


def test_a_mention_with_a_keyword_composes_the_configured_keyword(tmp_path):
    """
    Scenario: a mention with a keyword composes the configured keyword
      Given a room declared for #389
      When an authorized member posts "<@UBOT> start"
      Then `the-loop start` is recorded unmarked on the ticket as control.command
      And nothing is delivered — the ledger's ingress executes it
    """
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), Client()
    outcome = send(config, sink, client, addressed=True, text=f"<@{BOT}> start")
    assert outcome["event"] == "control.command" and outcome["mirrored"]
    body = sink.recorded[0][1]
    assert "the-loop start" in body and not is_self_authored(body)
    assert sink.delivered == []


def test_a_mentioned_top_level_message_in_the_central_channel_is_a_kickoff(tmp_path):
    """
    Scenario: a mentioned top-level message in the central channel is a kickoff
      Given the central channel holds work-item.create and a kickoff repo
      When an authorized member posts "<@UBOT> fix the flaky teardown" top-level
      Then an issue is created from the text after the mention
      When another member posts a plain top-level message
      Then nothing is created — it is not-addressed
    """
    config = config_for(tmp_path, kickoff={"repo": "octo/repo"})
    config["repositories"] = ["octo/repo"]
    sink, client = Sink(), Client()
    created = send(
        config,
        sink,
        client,
        addressed=True,
        channel=CENTRAL,
        text=f"<@{BOT}> fix the flaky teardown",
        ts="1900.1",
    )
    assert created["outcome"] == "created"
    assert sink.created == [("octo/repo", "fix the flaky teardown")]
    plain = send(
        config,
        sink,
        client,
        addressed=False,
        channel=CENTRAL,
        text="another idea",
        ts="1900.2",
    )
    assert plain == {"outcome": "not-addressed"} and len(sink.created) == 1


def test_a_redelivered_mention_is_processed_once(tmp_path):
    """
    Scenario: a redelivered mention is processed once
      Given a mention was processed
      When Slack redelivers the same app_mention
      Then it is dropped as duplicate
    """
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), Client()
    first = send(
        config, sink, client, addressed=True, text=f"<@{BOT}> hello", ts="1900.7"
    )
    again = send(
        config, sink, client, addressed=True, text=f"<@{BOT}> hello", ts="1900.7"
    )
    assert first["outcome"] == "processed" and again == {"outcome": "duplicate"}
    assert len(sink.delivered) == 1


def test_a_dm_hears_a_plain_message(tmp_path):
    """
    Scenario: a DM hears a plain message
      Given the central channel is the direct message with the bot
      And the-loop opened #389's thread there
      When a member replies without the mention
      Then it is input — Slack delivers no app_mention in a DM
    """
    config = config_for(tmp_path, channel=DM)
    sink, client = Sink(), Client()
    bot_for(config, client).bind("1800.1", REF, DM, origin="start")
    outcome = send(
        config,
        sink,
        client,
        addressed=False,
        channel=DM,
        text="use A",
        thread="1800.1",
        ts="1800.2",
    )
    assert outcome["outcome"] == "processed" and sink.delivered[0]["text"] == "use A"


def test_an_all_room_hears_a_plain_message_and_drops_the_mention_copy(tmp_path):
    """
    Scenario: an all room hears a plain message
      Given #389 declared C0TMP389 with --listen all
      When a member posts a plain message there
      Then it is input
      When Slack also delivers the app_mention copy of a mentioned message
      Then the plain copy is the input and the mention copy is the duplicate
    """
    config = config_for(tmp_path)
    declare(config, listen="all")
    sink, client = Sink(), Client()
    plain = send(config, sink, client, addressed=False, text="plain talk", ts="1900.1")
    assert plain["outcome"] == "processed"
    mention_copy = send(
        config, sink, client, addressed=True, text=f"<@{BOT}> hi", ts="1900.2"
    )
    assert mention_copy == {"outcome": "duplicate"}
    plain_copy = send(
        config, sink, client, addressed=False, text=f"<@{BOT}> hi", ts="1900.2"
    )
    assert plain_copy["outcome"] == "processed"
    assert sink.delivered[-1]["text"] == "hi"


def test_poll_mode_reads_no_mention_gated_conversation_and_moves_no_cursor(tmp_path):
    """
    Scenario: poll mode reads no mention-gated conversation and moves no cursor
      Given a bound thread in the central channel and a mentions room with messages
      When one poll cycle runs
      Then nothing is read from either, no cursor moves, and no room is baselined
      And a DM thread in the same cycle is read
    """
    config = config_for(tmp_path)
    config["channels"]["slack"]["read"] = {"mode": "poll"}
    declare(config)
    client = Client(
        replies={"1800.1": [{"ts": "1800.2", "user": "UHUMAN", "text": "use A"}]}
    )
    client.history = [{"ts": "1900.1", "user": "UHUMAN", "text": "room talk"}]
    sink = Sink()
    bot = bot_for(config, client)
    bot.bind("1800.1", REF, CENTRAL, origin="start")
    summary = inbound.poll_once(
        config,
        client_factory=lambda token: client,
        post_comment=sink.post_comment,
        deliver=sink.deliver,
    )
    assert summary["replies"] == 0 and sink.delivered == []
    state = _state_with_stores(
        Path(config["state"]["root"]) / "channels" / "slack.json"
    )
    assert state.cursors == {}


# -- R3: the grammar --------------------------------------------------------------------


def test_help_answers_ephemerally_and_records_nothing(tmp_path):
    """
    Scenario: help answers ephemerally and records nothing
      When a collaborator or an authorized member mentions "help"
      Then the grammar reaches only them, and nothing is recorded or delivered
    """
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), Client()
    outcome = send(config, sink, client, addressed=True, text=f"<@{BOT}> help")
    assert outcome["outcome"] == "answered" and outcome["answered"]
    assert client.ephemeral and "record-context" in client.ephemeral[0][2]
    assert client.ephemeral[0][1] == "UHUMAN"
    assert sink.recorded == [] and sink.delivered == []


# -- R4: record-context ------------------------------------------------------------------


def _thread_client():
    return Client(
        replies={
            "1800.1": [
                {"ts": "1800.1", "user": "UHUMAN", "text": "should we keep poll mode?"},
                {
                    "ts": "1800.2",
                    "user": "UOTHER",
                    "text": "<!channel> the-loop start now",
                },
                {"ts": "1800.3", "user": BOT, "text": "noted"},
            ]
        }
    )


def test_record_context_snapshots_a_thread_onto_the_ticket_and_into_the_session(
    tmp_path,
):
    """
    Scenario: record-context snapshots a thread onto the ticket and into the session
      Given a thread of three messages in the room
      When an authorized member mentions "record-context" in it
      Then the ticket gets a marked context.added record quoting the thread, scrubbed
      And the session is delivered the snapshot under the context frame
      And the thread gets one reply with the record's link, and the message ✅
    """
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), _thread_client()
    outcome = send(
        config,
        sink,
        client,
        addressed=True,
        text=f"<@{BOT}> record-context",
        thread="1800.1",
        ts="1800.4",
    )
    assert outcome["outcome"] == "processed" and outcome["event"] == "context.added"
    body = sink.recorded[0][1]
    assert is_self_authored(body)
    envelope = parse_envelope(body)
    assert envelope is not None and envelope.type == "context.added"
    assert "should we keep poll mode?" in body and "@the-loop" in body
    assert "the-loop start" not in body  # defanged
    assert "<!channel>" not in body  # neutralised
    assert "3 message" in body
    delivered = sink.delivered[0]
    assert delivered["kind"] == "context" and delivered["detail"]["count"] == "3"
    assert "issuecomment-1" in delivered["detail"]["url"]
    assert (
        "https://x.slack.com/archives/C0TMP389/p18001" in delivered["detail"]["thread"]
    )
    assert client.posted[-1]["thread_ts"] == "1800.1"
    assert "issuecomment-1" in client.posted[-1]["text"]
    assert client.reactions[-1][2] == "white_check_mark"


def test_record_context_on_a_top_level_message_snapshots_that_message(tmp_path):
    """
    Scenario: record-context on a top-level message snapshots that message
    """
    config = config_for(tmp_path)
    declare(config)
    client = Client(
        replies={
            "1900.9": [
                {"ts": "1900.9", "user": "UHUMAN", "text": f"<@{BOT}> record-context"}
            ]
        }
    )
    sink = Sink()
    outcome = send(
        config,
        sink,
        client,
        addressed=True,
        text=f"<@{BOT}> record-context",
        ts="1900.9",
    )
    assert outcome["outcome"] == "processed"
    assert sink.delivered[0]["detail"]["count"] == "1"


def test_a_second_record_context_records_only_what_is_new(tmp_path):
    """
    Scenario: a second record-context records only what is new
      Given a thread was recorded as context
      When record-context is mentioned again with nothing new
      Then nothing is recorded and the member is told so ephemerally
      When a new message arrives and record-context is mentioned again
      Then only that message is recorded
    """
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), _thread_client()
    send(
        config,
        sink,
        client,
        addressed=True,
        text=f"<@{BOT}> record-context",
        thread="1800.1",
        ts="1800.4",
    )
    again = send(
        config,
        sink,
        client,
        addressed=True,
        text=f"<@{BOT}> record-context",
        thread="1800.1",
        ts="1800.5",
    )
    assert again == {"outcome": "nothing-new", "event": "context.added"}
    assert len(sink.recorded) == 1 and "Nothing new" in client.ephemeral[-1][2]
    client.replies["1800.1"].append(
        {"ts": "1800.6", "user": "UHUMAN", "text": "one more"}
    )
    third = send(
        config,
        sink,
        client,
        addressed=True,
        text=f"<@{BOT}> record-context",
        thread="1800.1",
        ts="1800.7",
    )
    assert third["outcome"] == "processed"
    assert sink.delivered[-1]["detail"]["count"] == "1"
    assert (
        "one more" in sink.recorded[-1][1]
        and "keep poll mode" not in sink.recorded[-1][1]
    )


def test_record_context_without_the_grant_is_dropped_as_unpublishable(tmp_path):
    config = config_for(tmp_path, publish=["work-item.reply"])
    declare(config)
    sink, client = Sink(), _thread_client()
    outcome = send(
        config,
        sink,
        client,
        addressed=True,
        text=f"<@{BOT}> record-context",
        thread="1800.1",
        ts="1800.4",
    )
    assert outcome == {"outcome": "unpublishable-event"}
    assert sink.recorded == [] and sink.delivered == []


# -- R5: record-decision ----------------------------------------------------------------


def test_record_decision_lands_as_a_marked_record_and_a_decision_frame(tmp_path):
    """
    Scenario: record-decision lands as a marked record and a decision frame
      When an authorized member mentions "record-decision tech: keep poll mode — why: cheap"
      Then the ticket gets a marked decision.recorded record with the kind and rationale
      And the session is delivered the decision under the decision frame
    """
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), Client()
    outcome = send(
        config,
        sink,
        client,
        addressed=True,
        text=f"<@{BOT}> record-decision tech: keep poll mode — why: cheap",
        ts="1900.3",
    )
    assert outcome["outcome"] == "processed" and outcome["event"] == "decision.recorded"
    body = sink.recorded[0][1]
    assert is_self_authored(body) and "kind: tech" in body and "cheap" in body
    assert "> keep poll mode" in body
    assert envelope_of(body).type == "decision.recorded"
    delivered = sink.delivered[0]
    assert delivered["kind"] == "decision" and delivered["text"] == "keep poll mode"
    assert (
        delivered["detail"]["kind"] == "tech"
        and delivered["detail"]["rationale"] == "cheap"
    )
    assert "p19003" in delivered["detail"]["thread"]
    assert "📌" in client.posted[-1]["text"]


def test_an_empty_record_decision_is_refused_with_the_grammar(tmp_path):
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), Client()
    outcome = send(
        config, sink, client, addressed=True, text=f"<@{BOT}> record-decision"
    )
    assert outcome == {"outcome": "empty-decision"}
    assert sink.recorded == [] and "record-decision" in client.ephemeral[-1][2]
    assert client.reactions[-1][2] == "warning"


# -- R7: the tiers ------------------------------------------------------------------------


def _collaborator(config, slack="UCOLLAB", login=""):
    CollaboratorStore(portable(config)).add(
        REF, login=login, slack=slack, actor="octocat", source="cli"
    )


def test_a_collaborator_may_add_context_but_not_a_decision(tmp_path):
    """
    Scenario: a collaborator may add context but not a decision
      Given UCOLLAB is a collaborator on #389 by Slack id, and on no allow-list
      When UCOLLAB mentions "record-context" in a thread
      Then the snapshot is recorded, attributed to UCOLLAB by the envelope
      When UCOLLAB mentions "record-decision we ship"
      Then it is refused as unauthorized-act, with ⚠️ and an ephemeral line
      When UCOLLAB mentions "start"
      Then it is refused the same way
    """
    config = config_for(tmp_path)
    declare(config)
    _collaborator(config)
    sink, client = Sink(), _thread_client()
    ok = send(
        config,
        sink,
        client,
        addressed=True,
        text=f"<@{BOT}> record-context",
        thread="1800.1",
        ts="1800.4",
        user="UCOLLAB",
    )
    assert ok["outcome"] == "processed"
    assert envelope_of(sink.recorded[0][1]).actor == {"slack": "UCOLLAB"}
    refused = send(
        config,
        sink,
        client,
        addressed=True,
        text=f"<@{BOT}> record-decision we ship",
        ts="1900.5",
        user="UCOLLAB",
    )
    assert refused == {"outcome": "unauthorized-act"}
    assert (
        client.reactions[-1][2] == "warning"
        and "authorized user" in client.ephemeral[-1][2]
    )
    keyword = send(
        config,
        sink,
        client,
        addressed=True,
        text=f"<@{BOT}> start",
        ts="1900.6",
        user="UCOLLAB",
    )
    assert keyword == {"outcome": "unauthorized-act"}
    assert len(sink.recorded) == 1


def test_a_collaborators_record_names_the_rosters_ids(tmp_path):
    config = config_for(tmp_path)
    declare(config)
    _collaborator(config, slack="UCOLLAB", login="dana")
    sink, client = Sink(), Client()
    send(config, sink, client, addressed=True, text=f"<@{BOT}> hello", user="UCOLLAB")
    assert envelope_of(sink.recorded[0][1]).actor == {
        "slack": "UCOLLAB",
        "github": "dana",
    }


def test_a_roster_on_one_work_item_widens_nothing_on_another(tmp_path):
    """
    Scenario: a roster on one work item widens nothing on another
      Given UCOLLAB is a collaborator on #389 only
      When UCOLLAB mentions the-loop in #390's room
      Then it is dropped in silence
    """
    config = config_for(tmp_path)
    declare(config)
    declare(config, target="C0TMP390", work_item="github:octo/repo#390")
    _collaborator(config)
    sink, client = Sink(), Client()
    outcome = send(
        config,
        sink,
        client,
        addressed=True,
        channel="C0TMP390",
        text=f"<@{BOT}> hello",
        user="UCOLLAB",
    )
    assert outcome == {"outcome": "unauthorized-actor"}
    assert client.reactions == [] and client.ephemeral == []


# -- self-review round 1 (finding 1): the grammar is read only after an address ------


def test_a_plain_dm_that_starts_with_a_verb_is_a_reply(tmp_path):
    """
    Scenario: a plain message in a DM is the reply it always was
      Given the-loop asked a question in its DM with the operator
      When the operator answers "Do the second option" without the mention
      Then it is delivered as a reply — never composed into `the-loop do …`
    """
    config = config_for(tmp_path, channel=DM)
    sink, client = Sink(), Client()
    bot = bot_for(config, client)
    bot.bind("1800.1", REF, DM, origin="start")
    for i, text in enumerate(("Do the second option", "record-context", "help me")):
        outcome = send(
            config,
            sink,
            client,
            addressed=False,
            channel=DM,
            text=text,
            thread="1800.1",
            ts=f"1800.{i + 2}",
        )
        assert outcome["outcome"] == "processed", text
        assert outcome["event"] == "work-item.reply", text
    assert [d["text"] for d in sink.delivered] == [
        "Do the second option",
        "record-context",
        "help me",
    ]
    assert client.ephemeral == []


def test_a_mentioned_kickoff_keeps_its_body(tmp_path):
    """The title is the first line after the mention; the body keeps its lines."""
    config = config_for(tmp_path, kickoff={"repo": "octo/repo"})
    config["repositories"] = ["octo/repo"]
    sink, client = Sink(), Client()
    created = send(
        config,
        sink,
        client,
        addressed=True,
        channel=CENTRAL,
        text=f"<@{BOT}> fix the flaky teardown\n\nSteps to reproduce: run it twice",
        ts="1900.1",
    )
    assert created["outcome"] == "created"
    assert sink.created == [("octo/repo", "fix the flaky teardown")]


# -- self-review round 1 (findings 4 and 5) --------------------------------------------


def test_a_collaborators_plain_reply_is_input_whatever_the_gate(tmp_path):
    """
    Scenario: a collaborator's reply is input even while the item waits at a gate
      Given the channel holds gate.feedback and the graph cannot be read here
      When a collaborator mentions "I think option B"
      Then it is a work-item.reply, delivered — a collaborator cannot answer a gate
      And the same words from an authorized user are left to the ledger as gate.feedback
    """
    config = config_for(tmp_path, publish=[*GRANTS, "gate.feedback"])
    declare(config)
    _collaborator(config)
    sink, client = Sink(), Client()
    theirs = send(
        config,
        sink,
        client,
        addressed=True,
        text=f"<@{BOT}> I think option B",
        user="UCOLLAB",
        ts="1900.1",
    )
    assert theirs["outcome"] == "processed" and theirs["event"] == "work-item.reply"
    assert sink.delivered[-1]["text"] == "I think option B"
    ours = send(
        config,
        sink,
        client,
        addressed=True,
        text=f"<@{BOT}> I think option B",
        ts="1900.2",
    )
    assert ours["outcome"] == "processed" and ours["event"] == "gate.feedback"


def test_a_recording_act_in_a_standing_sessions_thread_is_refused_and_said(tmp_path):
    """A standing session has no ticket: `record-context` there is `no-ticket`
    with the reason, never a swallowed delivery error."""
    config = config_for(tmp_path, channel=DM)
    sink, client = Sink(), _thread_client()
    bot = bot_for(config, client)
    bot.bind("1800.1", "standing:review", DM, origin="start")
    # In a DM the plain copy is the input and carries the mention token (R1.6).
    outcome = send(
        config,
        sink,
        client,
        addressed=False,
        channel=DM,
        text=f"<@{BOT}> record-context",
        thread="1800.1",
        ts="1800.4",
    )
    assert outcome["outcome"] == "no-ticket"
    assert "standing session" in client.ephemeral[-1][2]
    assert sink.recorded == [] and sink.delivered == []
