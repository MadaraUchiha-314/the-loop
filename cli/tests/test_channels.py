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

    def chat_postMessage(self, *, channel, text, thread_ts=None):
        self.posted.append({"channel": channel, "text": text, "thread_ts": thread_ts})
        return {"ok": True, "channel": channel, "ts": f"1700.{len(self.posted):06d}"}

    def conversations_replies(self, *, channel, ts, oldest=None, limit=200):
        return {"ok": True, "messages": list(self.replies.get(ts, []))}

    def auth_test(self):
        return {"ok": True, "user_id": "UBOT"}


def cli_config(tmp_path, **slack):
    """A CLI config mapping with a channels.slack section and a temp state root."""
    section = {
        "enabled": True,
        "channel": "C123",
        "authorizedUsers": ["UHUMAN"],
        **slack,
    }
    return {"state": {"root": str(tmp_path / "state")}, "channels": {"slack": section}}


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
    assert list(config.events) == slack["events"]["default"]
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
    channel = make_channel(tmp_path, client, events=["dispatch.failed"])
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

    config = SlackChannelConfig.from_mapping(
        cli_config(tmp_path, authorizedUsers=list(authorized))
    )
    outcome = inbound.process_reply(
        reply, config, cli_config(tmp_path), post_comment=post_comment, deliver=deliver
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
    assert outcome == {"outcome": "processed", "mirrored": True, "delivered": True}
    assert posts[0][0] == "github:o/r#7"
    body = posts[0][1]
    assert is_self_authored(body)  # R1.3: dropped by ingress, never reprocessed
    assert "UHUMAN" in body and "lack" in body  # visible attribution names the channel
    assert "go with A" in body
    assert deliveries[0]["actor"] == "slack:UHUMAN"
    assert deliveries[0]["comment"] is False  # the mirror is the ticket record


def test_mirror_defangs_control_keywords(tmp_path):
    outcome, posts, _ = pipeline(tmp_path, a_reply(text="please the-loop start now"))
    body = posts[0][1]
    marker_free = body.split("<!--")[0]
    assert parse_command(marker_free, ControlConfig(enabled=True)).command is None


def test_undeliverable_reply_still_mirrors(tmp_path):
    outcome, posts, deliveries = pipeline(
        tmp_path, a_reply(), deliver_raises=LookupError("no session")
    )
    assert outcome == {"outcome": "processed", "mirrored": True, "delivered": False}
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
