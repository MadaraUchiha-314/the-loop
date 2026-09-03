"""Unit tests for the channels abstraction and the Slack bot provider (issue-245).

The pure core: config parsing (fail-closed), event filtering, verbosity
rendering, thread-binding state, the Slack channel against a fake client, and
the inbound pipeline steps. No test opens a network connection — the Slack SDK
boundary is the injected client factory (design D7).
"""

from __future__ import annotations

import json

import pytest

from the_loop import configschema, eventlog
from the_loop.authz import is_self_authored
from the_loop.channels import inbound
from the_loop.channels.base import (
    DEFAULT_EVENTS,
    ChannelError,
    InboundReply,
    OutboundEvent,
    load_channels,
    render,
)
from the_loop.channels.slack import (
    DEFAULT_APP_TOKEN_ENV,
    DEFAULT_BOT_TOKEN_ENV,
    SlackBotChannel,
    SlackChannelConfig,
)
from the_loop.channels.state import THREAD_CAP, ChannelState
from the_loop.control import ControlConfig, parse_command


class FakeSlackClient:
    """The slice of ``slack_sdk.WebClient`` the channel uses, recorded."""

    def __init__(self, token=None, replies=None):
        self.token = token
        self.posted = []
        self.replies = replies or {}  # thread ts -> [message dict, ...]
        self.history = []  # top-level messages, for the kickoff read

    def chat_postMessage(self, *, channel, text, thread_ts=None, blocks=None):
        self.posted.append(
            {"channel": channel, "text": text, "thread_ts": thread_ts, "blocks": blocks}
        )
        return {"ok": True, "channel": channel, "ts": f"1700.{len(self.posted):06d}"}

    def conversations_history(self, *, channel, oldest=None, limit=100):
        return {"ok": True, "messages": list(self.history)}

    def conversations_replies(self, *, channel, ts, oldest=None, limit=200):
        return {"ok": True, "messages": list(self.replies.get(ts, []))}

    def auth_test(self):
        return {"ok": True, "user_id": "UBOT"}


def cli_config(tmp_path, authorized=("UHUMAN",), **slack):
    """A CLI config mapping with a channels.slack section and a temp state root."""
    section = {"enabled": True, "channel": "C123", **slack}
    return {
        "state": {"root": str(tmp_path / "state")},
        # Identity in one place (issue-309): the Slack member id sits on a
        # person entry beside their GitHub login.
        "routing": {
            "authorizedUsers": [
                {"github": f"gh-{member}", "slack": member} for member in authorized
            ]
        },
        "channels": {"slack": section},
    }


def make_channel(tmp_path, client, **slack):
    config = SlackChannelConfig.from_mapping(cli_config(tmp_path, **slack))
    state_path = tmp_path / "state" / "channels" / "slack.json"
    return SlackBotChannel(config, state_path, client_factory=lambda token: client)


def event(text="Should I use approach A or B?", **kwargs):
    return OutboundEvent(
        event_type=kwargs.pop("event_type", "session.awaiting_input"),
        work_item="github:o/r#7",
        text=text,
        url=kwargs.pop("url", "https://github.com/o/r/issues/7#c1"),
        detail=kwargs.pop("detail", {"actor": "agent"}),
    )


# -- config parsing (R1.4, R6.1) ------------------------------------------------


def test_absent_section_yields_no_channels(tmp_path):
    assert load_channels({"state": {"root": str(tmp_path)}}) == []
    assert load_channels(None) == []


def test_disabled_section_yields_no_channels(tmp_path):
    assert load_channels(cli_config(tmp_path, enabled=False)) == []


def test_malformed_section_fails_closed(tmp_path, caplog):
    config = {"state": {"root": str(tmp_path)}, "channels": {"slack": "not-a-mapping"}}
    with caplog.at_level("ERROR", logger="the-loop.channels"):
        assert load_channels(config) == []
    assert any("channels" in r.message for r in caplog.records)


def test_config_defaults_match_the_schema():
    """R6.1: what ``from_mapping`` defaults and what the schema documents agree."""
    schema = configschema.load_schema("cli-config")
    slack = schema["properties"]["channels"]["properties"]["slack"]["properties"]
    config = SlackChannelConfig.from_mapping({})
    assert config.enabled is slack["enabled"]["default"] is False
    assert config.bot_token_env == slack["botTokenEnv"]["default"]
    assert config.app_token_env == slack["appTokenEnv"]["default"]
    assert config.verbosity == slack["verbosity"]["default"]
    assert list(config.subscribe) == slack["subscribe"]["default"]
    assert list(config.publish) == slack["publish"]["default"]
    assert config.max_chars == slack["maxChars"]["default"]
    assert config.kickoff_repo == slack["kickoff"]["properties"]["repo"]["default"]
    read = slack["read"]["properties"]
    assert config.read_mode == read["mode"]["default"]
    assert config.read_interval_seconds == read["intervalSeconds"]["default"]
    assert config.bot_token_env == DEFAULT_BOT_TOKEN_ENV
    assert config.app_token_env == DEFAULT_APP_TOKEN_ENV


def test_malformed_read_mode_resolves_off(tmp_path, caplog):
    """An unknown read mode never resolves to a *reading* mode."""
    config = SlackChannelConfig.from_mapping(
        cli_config(tmp_path, read={"mode": "telepathy"})
    )
    assert config.read_mode == "off"


# -- event filter + verbosity (R2.1, R2.2) --------------------------------------


def test_default_events_carry_the_ask(tmp_path):
    channel = make_channel(tmp_path, FakeSlackClient())
    assert DEFAULT_EVENTS == ("session.awaiting_input",)
    assert channel.wants("session.awaiting_input")
    assert not channel.wants("channel.posted")


def test_off_list_event_posts_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    channel = make_channel(tmp_path, client, subscribe=["dispatch.failed"])
    assert not channel.wants("session.awaiting_input")


def test_verbosity_renders_supersets():
    quiet = render(event(), "quiet")
    normal = render(event(), "normal")
    verbose = render(event(), "verbose")
    assert "github:o/r#7" in quiet and "https://github.com/o/r/issues/7#c1" in quiet
    assert "approach A or B" not in quiet
    assert quiet in normal and "approach A or B" in normal
    assert normal in verbose and "actor" in verbose


def test_unknown_verbosity_renders_normal():
    assert render(event(), "shouty") == render(event(), "normal")


# -- the Slack channel (R3.1–R3.3) ----------------------------------------------


def test_token_is_read_at_call_time(tmp_path, monkeypatch):
    seen = []
    channel = SlackBotChannel(
        SlackChannelConfig.from_mapping(cli_config(tmp_path)),
        tmp_path / "slack.json",
        client_factory=lambda token: seen.append(token) or FakeSlackClient(),
    )
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-late")
    channel.post(event())
    assert seen == ["xoxb-late"]


def test_missing_token_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv(DEFAULT_BOT_TOKEN_ENV, raising=False)
    channel = make_channel(tmp_path, FakeSlackClient())
    with pytest.raises(ChannelError) as excinfo:
        channel.post(event())
    assert DEFAULT_BOT_TOKEN_ENV in str(excinfo.value)


def test_missing_channel_id_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    channel = make_channel(tmp_path, FakeSlackClient(), channel="")
    with pytest.raises(ChannelError):
        channel.post(event())


def test_first_post_binds_a_thread_and_second_reuses_it(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    channel = make_channel(tmp_path, client)
    first = channel.post(event())
    second = channel.post(event(text="follow-up?"))
    assert client.posted[0]["thread_ts"] is None
    assert client.posted[1]["thread_ts"] == first.thread
    assert second.thread == first.thread
    state = ChannelState.load(tmp_path / "state" / "channels" / "slack.json")
    assert state.work_item_for(first.thread) == "github:o/r#7"


def test_token_never_lands_in_the_state_file(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-supersecret")
    channel = make_channel(tmp_path, FakeSlackClient())
    channel.post(event())
    raw = (tmp_path / "state" / "channels" / "slack.json").read_text()
    assert "xoxb-supersecret" not in raw


# -- binding state (D4) ---------------------------------------------------------


def test_state_round_trips_and_survives_restart(tmp_path):
    path = tmp_path / "slack.json"
    state = ChannelState.load(path)
    state.bind("1700.1", "github:o/r#7", "C123")
    state.advance("1700.1", "1700.5")
    state.save(path)
    reloaded = ChannelState.load(path)
    assert reloaded.work_item_for("1700.1") == "github:o/r#7"
    assert reloaded.cursor("1700.1") == "1700.5"


def test_state_caps_threads_dropping_the_oldest(tmp_path):
    state = ChannelState.load(tmp_path / "slack.json")
    for n in range(THREAD_CAP + 5):
        state.bind(f"1700.{n}", f"github:o/r#{n}", "C123")
    assert state.work_item_for("1700.0") is None
    assert (
        state.work_item_for(f"1700.{THREAD_CAP + 4}") == f"github:o/r#{THREAD_CAP + 4}"
    )


# -- fetching replies (R4.4–R4.6) -----------------------------------------------


def reply_fixture(tmp_path, monkeypatch, messages):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    channel = make_channel(tmp_path, client)
    posted = channel.post(event())
    client.replies[posted.thread] = [
        {"ts": posted.thread, "user": "UBOT", "text": "the question"},  # thread root
        *messages,
    ]
    return channel, posted.thread


def test_fetch_returns_only_new_replies_and_flags_bots(tmp_path, monkeypatch):
    channel, thread = reply_fixture(
        tmp_path,
        monkeypatch,
        [
            {"ts": "1800.1", "user": "UHUMAN", "text": "use A"},
            {"ts": "1800.2", "user": "UOTHER", "bot_id": "B99", "text": "beep"},
            {"ts": "1800.3", "user": "UBOT", "text": "own echo"},
        ],
    )
    replies = channel.fetch_replies()
    assert [r.ts for r in replies] == ["1800.1", "1800.2", "1800.3"]
    assert [r.is_bot for r in replies] == [False, True, True]
    assert replies[0].work_item == "github:o/r#7"
    assert replies[0].author == "UHUMAN"


def test_cursor_advance_means_processed_at_most_once(tmp_path, monkeypatch):
    channel, thread = reply_fixture(
        tmp_path, monkeypatch, [{"ts": "1800.1", "user": "UHUMAN", "text": "use A"}]
    )
    first = channel.fetch_replies()
    channel.advance(thread, first[-1].ts)
    assert channel.fetch_replies() == []


# -- the inbound pipeline (R1.3, R5) --------------------------------------------


def a_reply(**kwargs):
    return InboundReply(
        channel="slack",
        work_item=kwargs.pop("work_item", "github:o/r#7"),
        author=kwargs.pop("author", "UHUMAN"),
        text=kwargs.pop("text", "go with A"),
        thread="1700.1",
        ts=kwargs.pop("ts", "1800.1"),
        is_bot=kwargs.pop("is_bot", False),
    )


def pipeline(tmp_path, reply, *, authorized=("UHUMAN",), deliver_raises=None):
    posts, deliveries = [], []

    def post_comment(item, body, gh_binary="gh"):
        posts.append((item.ref, body))
        return True, ""

    def deliver(ref, text, actor="", comment=True, config=None):
        if deliver_raises is not None:
            raise deliver_raises
        deliveries.append(
            {"ref": ref, "text": text, "actor": actor, "comment": comment}
        )
        return {"delivered": True}

    config = SlackChannelConfig.from_mapping(cli_config(tmp_path, authorized))
    outcome = inbound.process_reply(
        reply,
        config,
        cli_config(tmp_path, authorized),
        post_comment=post_comment,
        deliver=deliver,
    )
    return outcome, posts, deliveries


def test_own_bot_message_is_dropped_before_anything(tmp_path):
    outcome, posts, deliveries = pipeline(tmp_path, a_reply(is_bot=True))
    assert outcome["outcome"] == "self-authored"
    assert posts == [] and deliveries == []


def test_empty_allowlist_denies_every_reply(tmp_path):
    outcome, posts, deliveries = pipeline(tmp_path, a_reply(), authorized=())
    assert outcome["outcome"] == "unauthorized-actor"
    assert posts == [] and deliveries == []


def test_unlisted_member_id_is_denied(tmp_path):
    outcome, posts, deliveries = pipeline(tmp_path, a_reply(author="UEVIL"))
    assert outcome["outcome"] == "unauthorized-actor"
    assert posts == [] and deliveries == []


def test_accepted_reply_is_mirrored_then_delivered(tmp_path):
    outcome, posts, deliveries = pipeline(tmp_path, a_reply())
    assert outcome == {
        "outcome": "processed",
        "event": "work-item.reply",
        "mirrored": True,
        "delivered": True,
    }
    assert posts[0][0] == "github:o/r#7"
    body = posts[0][1]
    assert is_self_authored(body)  # R1.3: dropped by ingress, never reprocessed
    assert "UHUMAN" in body and "lack" in body  # visible attribution names the channel
    assert "go with A" in body
    assert deliveries[0]["actor"] == "slack:UHUMAN"
    assert deliveries[0]["comment"] is False  # the mirror is the ticket record


def test_a_control_keyword_without_the_grant_is_dropped_not_delivered(tmp_path):
    """A2 (issue-309): dropped, never downgraded — the keyword reaches neither the
    ticket nor the agent when the channel may not publish `control.command`."""
    outcome, posts, deliveries = pipeline(
        tmp_path, a_reply(text="please the-loop start now")
    )
    assert outcome == {"outcome": "unpublishable-event"}
    assert posts == [] and deliveries == []


def test_a_control_keyword_with_the_grant_is_recorded_unmarked_for_ingress(tmp_path):
    """R3.5 (issue-309): with the grant the record is a HUMAN comment — no
    self-marker, the keyword intact — so the ledger's ingress executes it through
    the control seam; the pipeline itself delivers nothing."""
    reply = a_reply(text="please the-loop start now")
    posts, deliveries = [], []

    def post_comment(item, body, gh_binary="gh"):
        posts.append((item.ref, body))
        return True, "", "https://x/c1"

    config = SlackChannelConfig.from_mapping(
        cli_config(tmp_path, publish=["work-item.reply", "control.command"])
    )
    outcome = inbound.process_reply(
        reply,
        config,
        cli_config(tmp_path),
        post_comment=post_comment,
        deliver=lambda *a, **k: deliveries.append(a) or {"delivered": True},
    )
    assert outcome == {
        "outcome": "processed",
        "event": "control.command",
        "mirrored": True,
    }
    assert deliveries == []
    body = posts[0][1]
    assert not is_self_authored(body)
    assert parse_command(body, ControlConfig(enabled=True)).command == "start"
    from the_loop.channels.envelope import parse as parse_envelope

    envelope = parse_envelope(body)
    assert envelope is not None and envelope.type == "control.command"
    assert envelope.source == "slack"
    assert envelope.actor == {"github": "gh-UHUMAN", "slack": "UHUMAN"}


def test_undeliverable_reply_still_mirrors(tmp_path):
    outcome, posts, deliveries = pipeline(
        tmp_path, a_reply(), deliver_raises=LookupError("no session")
    )
    assert outcome == {
        "outcome": "processed",
        "event": "work-item.reply",
        "mirrored": True,
        "delivered": False,
    }
    assert len(posts) == 1 and deliveries == []


def test_event_payloads_never_carry_tokens_or_text(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-supersecret")
    log = tmp_path / "events.jsonl"
    eventlog.configure("test", path=log, enabled=True)
    try:
        pipeline(tmp_path, a_reply(text="the secret answer"))
    finally:
        eventlog.reset()
    raw = log.read_text()
    assert "channel.reply_received" in raw
    assert "xoxb-supersecret" not in raw
    assert "the secret answer" not in raw


def test_process_advances_nothing_it_did_not_see(tmp_path):
    """An unmapped reply (no binding) is dropped with a recorded reason."""
    outcome = inbound.process_reply(
        a_reply(work_item=""),
        SlackChannelConfig.from_mapping(cli_config(tmp_path)),
        cli_config(tmp_path),
        post_comment=lambda *a, **k: (True, ""),
        deliver=lambda *a, **k: {"delivered": True},
    )
    assert outcome["outcome"] == "unmapped"


# -- poll_once (R4.1) -----------------------------------------------------------


def test_poll_once_processes_and_advances(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    factory = lambda token: client  # noqa: E731

    channel = SlackBotChannel(
        SlackChannelConfig.from_mapping(config),
        tmp_path / "state" / "channels" / "slack.json",
        client_factory=factory,
    )
    posted = channel.post(event())
    client.replies[posted.thread] = [
        {"ts": posted.thread, "user": "UBOT", "text": "the question"},
        {"ts": "1800.1", "user": "UHUMAN", "text": "use A"},
    ]

    posts, deliveries = [], []
    summary = inbound.poll_once(
        config,
        client_factory=factory,
        post_comment=lambda item, body, gh_binary="gh": (
            posts.append(item.ref) or (True, "")
        ),
        deliver=lambda *a, **k: deliveries.append(a) or {"delivered": True},
    )
    assert summary["replies"] == 1 and summary["processed"] == 1
    assert posts == ["github:o/r#7"] and len(deliveries) == 1

    again = inbound.poll_once(
        config,
        client_factory=factory,
        post_comment=lambda *a, **k: (True, ""),
        deliver=lambda *a, **k: {"delivered": True},
    )
    assert again["replies"] == 0  # the cursor advanced — processed at most once


def test_poll_once_skips_when_disabled_or_off(tmp_path):
    assert inbound.poll_once({"state": {"root": str(tmp_path)}})["skipped"]
    assert inbound.poll_once(cli_config(tmp_path, read={"mode": "off"}))["skipped"]


# -- the channels CLI verb (D9) -------------------------------------------------


def test_channels_status_shows_presence_never_values(tmp_path, monkeypatch, capsys):
    from the_loop.commands.channels_cmd import ChannelsCommand

    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-supersecret")
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    (tmp_path / "cli-config.yaml").write_text(
        json.dumps(cli_config(tmp_path)), encoding="utf-8"
    )
    import argparse

    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    code = ChannelsCommand().run(parser.parse_args(["status"]))
    out = capsys.readouterr().out
    assert code == 0
    assert "slack" in out and "set" in out
    assert "xoxb-supersecret" not in out


# -- the subscribable-event catalog (PR #267 review) ----------------------------


def test_the_catalog_carries_the_ask_and_every_notification_event():
    """The common definition (PR #267 review): everything the notify hook can
    fire per the harness taxonomy is subscribable, plus the ask."""
    from the_loop.channels.events import NOTIFICATION_EVENTS, SUBSCRIBABLE_EVENTS

    assert "session.awaiting_input" in SUBSCRIBABLE_EVENTS
    for name in NOTIFICATION_EVENTS:
        assert name in SUBSCRIBABLE_EVENTS


def test_the_catalog_matches_the_harness_notification_taxonomy():
    """Containment is pinned against the schema, so a new notification event
    cannot ship without joining the catalog users configure against."""
    import json
    from pathlib import Path

    from the_loop.channels.events import NOTIFICATION_EVENTS

    schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / ".the-loop"
            / "harness-config.schema.json"
        ).read_text(encoding="utf-8")
    )
    taxonomy = schema["properties"]["notifications"]["properties"]["events"][
        "properties"
    ]
    assert set(taxonomy) == set(NOTIFICATION_EVENTS)


def test_the_docs_list_every_subscribable_event():
    """The doc page and the catalog cannot drift (the docs-parity ethos)."""
    from pathlib import Path

    from the_loop.channels.events import SUBSCRIBABLE_EVENTS

    doc = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "config"
        / "cli"
        / "channels-options.md"
    ).read_text(encoding="utf-8")
    for name in SUBSCRIBABLE_EVENTS:
        assert f"`{name}`" in doc, f"{name} missing from channels-options.md"


def test_an_unknown_event_name_warns_but_is_kept(tmp_path, caplog):
    """A typo must not fail SILENTLY (the allow-list would just eat the event);
    a custom graph's own notify event must still be subscribable."""
    with caplog.at_level("WARNING", logger="the-loop.channels"):
        config = SlackChannelConfig.from_mapping(
            cli_config(tmp_path, subscribe=["phase-approval-pending", "phse-typo"])
        )
    assert config.events == ("phase-approval-pending", "phse-typo")
    warning = "\n".join(r.getMessage() for r in caplog.records)
    assert "phse-typo" in warning and "channels status" in warning


def test_a_catalog_only_events_list_warns_nothing(tmp_path, caplog):
    with caplog.at_level("WARNING", logger="the-loop.channels"):
        SlackChannelConfig.from_mapping(
            cli_config(
                tmp_path, subscribe=["session.awaiting_input", "pr-review-pending"]
            )
        )
    assert not caplog.records


def test_channels_status_prints_the_catalog_with_ticks(tmp_path, monkeypatch, capsys):
    from the_loop.commands.channels_cmd import ChannelsCommand

    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    (tmp_path / "cli-config.yaml").write_text(
        json.dumps(cli_config(tmp_path, subscribe=["phase-approval-pending"])),
        encoding="utf-8",
    )
    import argparse

    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    assert ChannelsCommand().run(parser.parse_args(["status"])) == 0
    out = capsys.readouterr().out
    assert "[x] phase-approval-pending" in out
    assert "[ ] session.awaiting_input" in out


# -- the thread is the work item's (issue-312) ----------------------------------


def _state_path(tmp_path):
    return tmp_path / "state" / "channels" / "slack.json"


def _conversation(state, work_item):
    record = state.conversation(work_item)
    assert record is not None, f"no conversation for {work_item}"
    return record


def test_bind_records_the_conversation_per_work_item(tmp_path):
    """R3.1: one keyed record per work item, beside the reader's thread map."""
    path = tmp_path / "slack.json"
    state = ChannelState.load(path)
    state.bind(
        "1700.1", "github:o/r#7", "C123", origin="kickoff", permalink="https://s/p1"
    )
    state.save(path)
    reloaded = ChannelState.load(path)
    assert reloaded.thread_for("github:o/r#7") == ("C123", "1700.1")
    record = reloaded.conversation("github:o/r#7")
    assert record is not None
    assert record["channel"] == "C123" and record["thread"] == "1700.1"
    assert record["origin"] == "kickoff" and record["permalink"] == "https://s/p1"
    assert record["opened"].endswith("Z")
    assert reloaded.work_item_for("1700.1") == "github:o/r#7"
    assert reloaded.conversation("github:o/r#8") is None


def test_a_pre_issue_312_state_file_backfills_its_conversations(tmp_path):
    """R3.4: a threads-only file (13.0.1) still answers, and is rewritten keyed."""
    path = tmp_path / "slack.json"
    path.write_text(
        json.dumps(
            {
                "threads": {
                    "1700.1": {"workItem": "github:o/r#7", "channel": "C123"},
                    "1700.2": {"workItem": "github:o/r#7", "channel": "C123"},
                },
                "cursors": {"1700.1": "1700.5"},
            }
        ),
        encoding="utf-8",
    )
    state = ChannelState.load(path)
    assert state.thread_for("github:o/r#7") == ("C123", "1700.2")  # newest binding
    assert _conversation(state, "github:o/r#7")["origin"] == "legacy"
    state.save(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["conversations"]["github:o/r#7"]["thread"] == "1700.2"
    assert raw["cursors"] == {"1700.1": "1700.5"}  # untouched


def test_a_ref_spelled_with_the_default_host_shares_the_thread(tmp_path):
    """R1.3: one work item, two spellings of its ref, one conversation."""
    state = ChannelState.load(tmp_path / "slack.json")
    state.bind("1700.1", "github:o/r#7", "C123")
    assert state.thread_for("github:github.com/o/r#7") == ("C123", "1700.1")
    assert _conversation(state, "github:github.com/o/r#7")["thread"] == "1700.1"
    state.bind("1700.2", "github:github.com/o/r#7", "C123")
    assert state.work_item_for("1700.2") == "github:o/r#7"
    assert len(state.conversations) == 1
    assert state.thread_for("standing:supervisor") is None


def test_eviction_drops_the_conversation_with_the_thread(tmp_path):
    state = ChannelState.load(tmp_path / "slack.json")
    for n in range(THREAD_CAP + 1):
        state.bind(f"1700.{n}", f"github:o/r#{n}", "C123")
    assert state.work_item_for("1700.0") is None
    assert state.conversation("github:o/r#0") is None
    assert state.thread_for("github:o/r#0") is None
    assert state.conversation(f"github:o/r#{THREAD_CAP}") is not None


def test_locked_sections_on_one_path_serialize(tmp_path):
    """R1.4: the second writer waits for the first's critical section."""
    import threading
    import time

    path = tmp_path / "slack.json"
    order = []

    def first():
        with ChannelState.locked(path) as state:
            order.append("first-in")
            time.sleep(0.2)
            state.bind("1700.1", "github:o/r#7", "C123")
            state.save(path)
            order.append("first-out")

    def second():
        time.sleep(0.05)
        with ChannelState.locked(path) as state:
            order.append("second-in")
            assert state.thread_for("github:o/r#7") == ("C123", "1700.1")

    a, b = threading.Thread(target=first), threading.Thread(target=second)
    a.start()
    b.start()
    a.join()
    b.join()
    assert order == ["first-in", "first-out", "second-in"]
    assert (tmp_path / "slack.json.lock").exists()


def test_without_flock_the_lock_degrades_to_today(tmp_path, monkeypatch, caplog):
    """A5: no `flock` on the platform — one debug line, an unlocked section, delivery."""
    from the_loop import runlock

    monkeypatch.setattr(runlock, "HAVE_FLOCK", False)
    path = tmp_path / "slack.json"
    with caplog.at_level("DEBUG", logger="the-loop.channels"):
        with ChannelState.locked(path) as state:
            state.bind("1700.1", "github:o/r#7", "C123")
            state.save(path)
    assert ChannelState.load(path).thread_for("github:o/r#7") == ("C123", "1700.1")
    assert any("flock" in rec.message for rec in caplog.records)


def test_the_first_post_opens_a_root_and_replies_into_it(tmp_path, monkeypatch):
    """R1.1, R1.2: the root names the work item; the event is the first reply."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    channel = make_channel(tmp_path, client)
    result = channel.post(event())
    assert len(client.posted) == 2
    root, reply = client.posted
    assert root["thread_ts"] is None and root["channel"] == "C123"
    assert root["blocks"][0]["type"] == "header"
    assert "github:o/r#7" in root["blocks"][0]["text"]["text"]
    assert "https://github.com/o/r/issues/7" in root["blocks"][1]["text"]["text"]
    assert root["blocks"][-1]["type"] == "actions"
    assert root["blocks"][-1]["elements"][0]["url"] == "https://github.com/o/r/issues/7"
    assert "github:o/r#7" in root["text"]
    assert reply["thread_ts"] == "1700.000001" == result.thread
    assert reply["blocks"][0]["text"]["text"].startswith("Question from the agent")
    assert "approach A or B" in reply["text"]
    record = _conversation(ChannelState.load(_state_path(tmp_path)), "github:o/r#7")
    assert record == {
        "channel": "C123",
        "thread": "1700.000001",
        "opened": record["opened"],
        "origin": "event",
        "permalink": "",
    }


def test_the_second_post_is_one_reply(tmp_path, monkeypatch):
    """R1.3: a bound work item never gets a second top-level message."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    channel = make_channel(tmp_path, client)
    first = channel.post(event())
    second = channel.post(event(text="follow-up?", event_type="comment.agent"))
    assert len(client.posted) == 3
    assert client.posted[2]["thread_ts"] == first.thread == second.thread
    assert [p["thread_ts"] for p in client.posted].count(None) == 1


def test_a_standing_ref_gets_a_bare_root_and_no_link(tmp_path, monkeypatch):
    """R1.6: a ref that is not a work item is named as it is, with no button."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    channel = make_channel(tmp_path, client)
    channel.post(
        OutboundEvent(
            event_type="standing.started", work_item="standing:supervisor", text="up"
        )
    )
    root = client.posted[0]
    assert "standing:supervisor" in root["blocks"][0]["text"]["text"]
    assert all(block["type"] != "actions" for block in root["blocks"])
    assert client.posted[1]["thread_ts"] == "1700.000001"


def test_the_root_says_replies_reach_it_only_when_the_channel_reads(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    reading = FakeSlackClient()
    make_channel(tmp_path, reading).post(event())
    assert "Replies" in reading.posted[0]["blocks"][1]["text"]["text"]
    off = FakeSlackClient()
    make_channel(tmp_path / "off", off, read={"mode": "off"}).post(event())
    assert "Replies" not in off.posted[0]["blocks"][1]["text"]["text"]


def test_a_failed_reply_opens_no_second_thread(tmp_path, monkeypatch):
    """R2.3: a transient failure is a ChannelError, never a new root."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")

    class Flaky(FakeSlackClient):
        fail_replies = False

        def chat_postMessage(self, *, channel, text, thread_ts=None, blocks=None):
            if thread_ts is not None and self.fail_replies:
                raise RuntimeError("ratelimited")
            return super().chat_postMessage(
                channel=channel, text=text, thread_ts=thread_ts, blocks=blocks
            )

    client = Flaky()
    channel = make_channel(tmp_path, client)
    first = channel.post(event())
    client.fail_replies = True
    with pytest.raises(ChannelError):
        channel.post(event(text="again"))
    assert [p["thread_ts"] for p in client.posted].count(None) == 1
    state = ChannelState.load(_state_path(tmp_path))
    assert state.thread_for("github:o/r#7") == ("C123", first.thread)


def test_a_failed_root_binds_nothing_and_the_next_event_retries(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")

    class RootFails(FakeSlackClient):
        fail_root = False

        def chat_postMessage(self, *, channel, text, thread_ts=None, blocks=None):
            if thread_ts is None and self.fail_root:
                raise RuntimeError("channel_not_found")
            return super().chat_postMessage(
                channel=channel, text=text, thread_ts=thread_ts, blocks=blocks
            )

    client = RootFails()
    client.fail_root = True
    channel = make_channel(tmp_path, client)
    with pytest.raises(ChannelError):
        channel.post(event())
    assert ChannelState.load(_state_path(tmp_path)).conversation("github:o/r#7") is None
    client.fail_root = False
    result = channel.post(event())
    assert result.ok and result.thread == "1700.000001"


def test_thread_opened_is_emitted_with_ids_only(tmp_path, monkeypatch):
    """R3.2: channel, work item, thread, channel id, origin — never text."""
    from the_loop.channels import slack as slack_mod

    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    events = []
    monkeypatch.setattr(
        slack_mod.eventlog,
        "emit",
        lambda name, level="info", **f: events.append((name, f)),
    )
    channel = make_channel(tmp_path, FakeSlackClient())
    channel.post(event(text="secret question text"))
    channel.post(event(text="second"))
    opened = [f for name, f in events if name == "channel.thread_opened"]
    assert len(opened) == 1
    assert opened[0]["channel"] == "slack" and opened[0]["work_item"] == "github:o/r#7"
    assert opened[0]["thread"] == "1700.000001" and opened[0]["channel_id"] == "C123"
    assert opened[0]["origin"] == "event"
    assert "secret question text" not in json.dumps(opened[0])


def test_the_permalink_is_recorded_when_slack_returns_one(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")

    class WithPermalink(FakeSlackClient):
        def chat_getPermalink(self, *, channel, message_ts):
            return {
                "ok": True,
                "permalink": f"https://x.slack.com/{channel}/p{message_ts}",
            }

    channel = make_channel(tmp_path, WithPermalink())
    channel.post(event())
    record = _conversation(ChannelState.load(_state_path(tmp_path)), "github:o/r#7")
    assert record["permalink"] == "https://x.slack.com/C123/p1700.000001"


def test_a_failed_permalink_still_binds_the_thread(tmp_path, monkeypatch):
    """A3: the nicety fails; the binding and the delivery stand."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")

    class PermalinkBroken(FakeSlackClient):
        def chat_getPermalink(self, *, channel, message_ts):
            raise RuntimeError("missing_scope")

    client = PermalinkBroken()
    result = make_channel(tmp_path, client).post(event())
    assert result.ok and len(client.posted) == 2
    record = _conversation(ChannelState.load(_state_path(tmp_path)), "github:o/r#7")
    assert record["thread"] == "1700.000001" and record["permalink"] == ""


def test_the_root_is_built_from_the_ref_alone(tmp_path, monkeypatch):
    """A2: an event's text and detail never reach the root."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    make_channel(tmp_path, client).post(
        event(
            text="<https://evil.example|click me> *bold* github:o/r#99",
            detail={"author": "mallory", "excerpt": "https://evil.example/x"},
        )
    )
    root = json.dumps(client.posted[0])
    assert "evil.example" not in root and "mallory" not in root
    assert "github:o/r#99" not in root


def test_a_corrupt_state_file_opens_a_fresh_thread(tmp_path, monkeypatch):
    """A4: garbage on disk loads as empty; the next event binds cleanly."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    path = _state_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    client = FakeSlackClient()
    result = make_channel(tmp_path, client).post(event())
    assert result.ok and client.posted[0]["thread_ts"] is None
    assert ChannelState.load(path).thread_for("github:o/r#7") == ("C123", result.thread)


def test_a_members_root_shaped_message_binds_nothing(tmp_path, monkeypatch):
    """A1: a top-level message that looks like the-loop's root is not a binding."""
    from the_loop.channels import inbound

    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)
    config = cli_config(tmp_path)
    client.history = [
        {
            "ts": "1600.1",
            "user": "UHUMAN",
            "text": "the-loop · github:o/r#7 — this thread carries every message",
        }
    ]
    inbound.poll_once(config)
    inbound.poll_once(config)
    state = ChannelState.load(_state_path(tmp_path))
    assert state.threads == {} and state.conversation("github:o/r#7") is None
    result = make_channel(tmp_path, client).post(event())
    assert result.thread != "1600.1"


def _threads_command(tmp_path, monkeypatch, *argv):
    from the_loop.commands.channels_cmd import ChannelsCommand
    import argparse

    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    (tmp_path / "cli-config.yaml").write_text(
        json.dumps(cli_config(tmp_path)), encoding="utf-8"
    )
    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    return ChannelsCommand().run(parser.parse_args(list(argv)))


def test_channels_threads_lists_and_filters_conversations(
    tmp_path, monkeypatch, capsys
):
    """R3.3: every conversation, one of them, or the records as JSON."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    channel = make_channel(tmp_path, FakeSlackClient())
    channel.post(event())
    channel.bind("1600.2", "github:o/r#42", "C123", origin="kickoff")

    assert _threads_command(tmp_path, monkeypatch, "threads") == 0
    out = capsys.readouterr().out
    assert "github:o/r#7" in out and "1700.000001" in out and "event" in out
    assert "github:o/r#42" in out and "1600.2" in out and "kickoff" in out

    assert (
        _threads_command(
            tmp_path, monkeypatch, "threads", "--work-item", "github:o/r#42"
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "github:o/r#42" in out and "github:o/r#7" not in out

    assert (
        _threads_command(
            tmp_path, monkeypatch, "threads", "--work-item", "github:github.com/o/r#42"
        )
        == 0
    )
    assert (
        "github:o/r#42" in capsys.readouterr().out
    )  # the default host is one spelling

    assert (
        _threads_command(
            tmp_path, monkeypatch, "threads", "--work-item", "github:o/r#9"
        )
        == 1
    )
    assert "no conversation" in capsys.readouterr().out

    assert _threads_command(tmp_path, monkeypatch, "threads", "--json") == 0
    records = json.loads(capsys.readouterr().out)
    assert {r["workItem"] for r in records} == {"github:o/r#7", "github:o/r#42"}
    assert "xoxb-test" not in json.dumps(records)


def test_channels_status_counts_work_items(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    make_channel(tmp_path, FakeSlackClient()).post(event())
    assert _threads_command(tmp_path, monkeypatch, "status") == 0
    assert "1 work item(s)" in capsys.readouterr().out


# -- the start opens the conversation (issue-317) --------------------------------


def _emitted(monkeypatch):
    from the_loop.channels import slack as slack_mod

    events = []
    monkeypatch.setattr(
        slack_mod.eventlog,
        "emit",
        lambda name, level="info", **f: events.append((name, f)),
    )
    return events


def test_open_posts_the_root_alone_and_binds_with_origin_start(tmp_path, monkeypatch):
    """R1.2, R2.1, R2.2: a start posts the root and nothing else; the record says
    `start`; `channel.thread_opened` carries ids only."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    events = _emitted(monkeypatch)
    client = FakeSlackClient()
    result = make_channel(tmp_path, client).open("github:o/r#7")
    assert result.ok and result.channel == "slack" and result.thread == "1700.000001"
    assert len(client.posted) == 1
    root = client.posted[0]
    assert root["thread_ts"] is None and root["channel"] == "C123"
    assert root["blocks"][0]["type"] == "header"
    assert "github:o/r#7" in root["blocks"][0]["text"]["text"]
    assert root["blocks"][-1]["elements"][0]["url"] == "https://github.com/o/r/issues/7"
    record = _conversation(ChannelState.load(_state_path(tmp_path)), "github:o/r#7")
    assert record["origin"] == "start" and record["thread"] == "1700.000001"
    opened = [f for name, f in events if name == "channel.thread_opened"]
    assert opened == [
        {
            "channel": "slack",
            "work_item": "github:o/r#7",
            "thread": "1700.000001",
            "channel_id": "C123",
            "origin": "start",
        }
    ]


def test_open_is_idempotent_for_a_bound_work_item(tmp_path, monkeypatch):
    """R1.3: a second start, and a start after an event, post nothing."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    channel = make_channel(tmp_path, client)
    first = channel.open("github:o/r#7")
    again = channel.open("github:o/r#7")
    assert again.ok and again.thread == first.thread and len(client.posted) == 1
    # A thread an event opened is kept, origin and all.
    other = FakeSlackClient()
    bound = make_channel(tmp_path, other, channel="C9")
    eight = OutboundEvent(
        event_type="session.awaiting_input", work_item="github:o/r#8", text="A or B?"
    )
    posted = bound.post(eight)
    assert len(other.posted) == 2  # root + reply
    assert bound.open("github:o/r#8").thread == posted.thread
    assert len(other.posted) == 2
    record = _conversation(ChannelState.load(_state_path(tmp_path)), "github:o/r#8")
    assert record["origin"] == "event"


def test_open_fails_closed_like_post(tmp_path, monkeypatch):
    """R1.5: no channel id and no token refuse before any call, as `post` does."""
    client = FakeSlackClient()
    monkeypatch.delenv(DEFAULT_BOT_TOKEN_ENV, raising=False)
    with pytest.raises(ChannelError, match="no bot token"):
        make_channel(tmp_path, client).open("github:o/r#7")
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    with pytest.raises(ChannelError, match="no channel id"):
        make_channel(tmp_path, client, channel="").open("github:o/r#7")
    assert client.posted == []
    assert ChannelState.load(_state_path(tmp_path)).conversation("github:o/r#7") is None


def test_a_failed_open_binds_nothing(tmp_path, monkeypatch):
    """R1.5: a root that fails to post is a ChannelError and no binding — the
    next event opens the thread lazily, as before."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")

    class Down(FakeSlackClient):
        def chat_postMessage(self, **kwargs):
            raise RuntimeError("slack is down")

    with pytest.raises(ChannelError, match="could not open a thread"):
        make_channel(tmp_path, Down()).open("github:o/r#7")
    assert ChannelState.load(_state_path(tmp_path)).conversation("github:o/r#7") is None
    client = FakeSlackClient()
    result = make_channel(tmp_path, client).post(event())
    assert result.ok and len(client.posted) == 2  # root, then the reply


def test_a_corrupt_state_file_still_opens_on_start(tmp_path, monkeypatch):
    """A5: garbage on disk loads as empty; the start binds a fresh root cleanly."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    path = _state_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    client = FakeSlackClient()
    result = make_channel(tmp_path, client).open("github:o/r#7")
    assert result.ok and len(client.posted) == 1
    assert ChannelState.load(path).thread_for("github:o/r#7") == ("C123", result.thread)


def test_an_unknown_origin_is_coerced_to_event(tmp_path):
    """R2.1 / T10: `start` is a known origin; anything else reads as `event`, so
    a record written by a newer version is still a valid one to an older reader."""
    state = ChannelState()
    state.bind("1.1", "github:o/r#7", "C123", origin="start")
    state.bind("1.2", "github:o/r#8", "C123", origin="bogus")
    assert _conversation(state, "github:o/r#7")["origin"] == "start"
    assert _conversation(state, "github:o/r#8")["origin"] == "event"
    state.save(_state_path(tmp_path))
    reloaded = ChannelState.load(_state_path(tmp_path))
    assert _conversation(reloaded, "github:o/r#7")["origin"] == "start"
