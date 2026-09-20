"""Unit and integration tests for issue-393 F2 — the deployment-wide Slack doctor.

Three requirements, in the order an operator meets them
(``docs/specs/issue-393/requirements.md`` R2.1–R2.3):

1. the scope probe names the events the manifest is expected to carry and says,
   in fixed words, that no API call can verify them;
2. ``doctor slack`` posts nonce heartbeats and reads how many came back — from
   the running listener's event log, or over its own connection — and calls a
   shortfall *evidence* of a second Socket Mode consumer, never proof;
3. ``doctor slack`` resolves every declared channel in the bot's own directory
   and reports each miss (the B1 failure class), naming a truncated listing.

No network: every Slack boundary is a fake that records its calls, as the rest
of ``test_channels*.py`` does. Spec: docs/specs/issue-393/testing-plan.md T1.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from the_loop import eventlog
from the_loop.channels import doctor as doctor_mod
from the_loop.channels import slack as slack_mod
from the_loop.channels.directory import SlackDirectory
from the_loop.channels.doctor import (
    check_declared_channels,
    consumer_verdict_text,
    probe_second_consumer,
)
from the_loop.channels.slack import (
    DEFAULT_APP_TOKEN_ENV,
    DEFAULT_BOT_TOKEN_ENV,
    EVENTS_UNVERIFIABLE_CAVEAT,
    HEARTBEAT_MARKER,
    SlackChannelConfig,
    expected_bot_events,
    heartbeat_nonce,
    heartbeat_text,
    probe_subscription,
)

MANIFEST = Path(slack_mod.__file__).with_name("slack-app-manifest.yaml")


def cli_config(tmp_path, channel="C0CENTRAL", **slack):
    section = {
        "enabled": True,
        "channel": channel,
        "publish": ["gate.feedback", "control.command", "work-item.create"],
        "read": {"mode": "socket"},
        **slack,
    }
    return {
        "state": {"root": str(tmp_path / "state")},
        "eventLog": {"enabled": True, "path": str(tmp_path / "events.jsonl")},
        "repositories": ["octocat/hello-world"],
        "routing": {"authorizedUsers": [{"github": "gh-UHUMAN", "slack": "UHUMAN"}]},
        "channels": {"slack": section},
    }


# -- fakes ---------------------------------------------------------------------------


class FakeResponse(dict):
    def __init__(self, payload, scopes):
        super().__init__(payload)
        self.headers = {"x-oauth-scopes": scopes}


class FakeSocket:
    """Enough of ``SocketModeClient`` for the doctor's own connection."""

    def __init__(self, app_token=None, web_client=None):
        self.app_token = app_token
        self.web_client = web_client
        self.socket_mode_request_listeners = []
        self.connected = False
        self.closed = False
        self.acks = []

    def connect(self):
        self.connected = True

    def close(self):
        self.closed = True

    def send_socket_mode_response(self, response):
        self.acks.append(response)

    def deliver(self, event):
        request = SimpleNamespace(type="events_api", envelope_id="env", payload={"event": event})
        for listener in self.socket_mode_request_listeners:
            listener(self, request)


class FakeDoctorClient:
    """``chat.postMessage`` / ``chat.delete`` / ``auth.test``, recorded — and, in
    place of Slack, the echo: each posted heartbeat is delivered back to the
    doctor's socket or appended to the listener's log **when ``echo`` says so**,
    which is how a test decides how many consumers "share" the token."""

    def __init__(self, echo=lambda index: True, log_path=None, channels=None):
        self.echo = echo
        self.log_path = log_path
        self.socket = None
        self.posted = []
        self.deleted = []
        self._channels = channels if channels is not None else [
            {"id": "C0CENTRAL", "name": "the-loop"},
            {"id": "GTEST", "name": "test-room"},
        ]

    def chat_postMessage(self, *, channel, text):
        index = len(self.posted)
        ts = f"1700000000.{index:06d}"
        self.posted.append({"channel": channel, "text": text, "ts": ts})
        if self.echo(index):
            event = {
                "type": "message",
                "bot_id": "B0BOT",
                "user": "UBOT",
                "channel": channel,
                "text": text,
                "ts": ts,
            }
            if self.socket is not None:
                self.socket.deliver(event)
            if self.log_path is not None:
                nonce = text.split()[-1]
                record = {"ts": "2026-09-19T00:00:00Z", "event": "channel.heartbeat", "nonce": nonce}
                with open(self.log_path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record) + "\n")
        return {"ok": True, "ts": ts, "channel": channel}

    def chat_delete(self, *, channel, ts):
        self.deleted.append(ts)
        return {"ok": True}

    def auth_test(self):
        return FakeResponse({"ok": True, "user_id": "UBOT"}, "chat:write,groups:history")

    def conversations_info(self, *, channel):
        return {"ok": True, "channel": {"id": channel, "is_private": True}}

    def users_conversations(self, *, types, exclude_archived, limit, cursor=None):
        return {"channels": list(self._channels), "response_metadata": {}}

    def conversations_list(self, *, types, exclude_archived, limit, cursor=None):
        return {"channels": [], "response_metadata": {"next_cursor": ""}}


@pytest.fixture
def tokens(monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-supersecret")
    monkeypatch.setenv(DEFAULT_APP_TOKEN_ENV, "xapp-supersecret")


# -- R2.1: the expected events, and the caveat -----------------------------------------


def test_expected_bot_events_are_read_from_the_packaged_manifest():
    """R2.1: the list comes from the one file an operator imports — so it can
    never drift from what the manifest actually declares."""
    declared = yaml.safe_load(MANIFEST.read_text())["settings"]["event_subscriptions"][
        "bot_events"
    ]
    assert expected_bot_events() == tuple(declared)
    assert "app_mention" in expected_bot_events()
    assert "message.im" in expected_bot_events()


def test_the_probe_result_carries_the_expected_events(tmp_path, tokens):
    """R2.1: the probe's answer names the events beside the scopes — and still
    makes only its two fixed calls (bugfix §AC4 of issue-362 stands)."""
    client = FakeDoctorClient()
    calls = []
    client.conversations_info = lambda *, channel: calls.append("info") or {  # type: ignore[method-assign]
        "ok": True,
        "channel": {"id": channel, "is_private": True},
    }
    original = client.auth_test
    client.auth_test = lambda: calls.append("auth") or original()  # type: ignore[method-assign]
    config = SlackChannelConfig.from_mapping(cli_config(tmp_path))
    result = probe_subscription(config, client_factory=lambda token: client)
    assert result["events"] == expected_bot_events()
    assert calls == ["info", "auth"]


def test_the_caveat_says_events_are_unverifiable_and_how_to_test_them():
    """R2.1: fixed words — an operator must read that the API cannot confirm
    the subscription, and that a mention is the test."""
    assert "not verifiable" in EVENTS_UNVERIFIABLE_CAVEAT
    assert "mention" in EVENTS_UNVERIFIABLE_CAVEAT
    assert "ok" not in EVENTS_UNVERIFIABLE_CAVEAT.split()  # never dressed as a pass


def run_status(tmp_path, monkeypatch, capsys, config, *argv):
    from the_loop.commands.channels_cmd import ChannelsCommand

    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    (tmp_path / "cli-config.yaml").write_text(json.dumps(config), encoding="utf-8")
    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    assert ChannelsCommand().run(parser.parse_args(["status", *argv])) == 0
    return capsys.readouterr().out


def test_status_probe_prints_the_events_next_to_the_scope_probe(
    tmp_path, monkeypatch, capsys, tokens
):
    """
    Feature: the deployment can diagnose itself
      Scenario: the scope probe names the expected events and their caveat
        Given a socket-mode channel and a bot token
        When `the-loop channels status --probe` runs
        Then the events line follows the probe line and names every manifest event
         And it states the subscription is not verifiable through the API
         And it says to test with a mention

    Requirement: docs/specs/issue-393/requirements.md R2.1
    """
    client = FakeDoctorClient()
    monkeypatch.setattr(slack_mod, "build_client", lambda token: client)
    out = run_status(tmp_path, monkeypatch, capsys, cli_config(tmp_path), "--probe")
    lines = out.splitlines()
    probe_at = next(i for i, line in enumerate(lines) if line.startswith("  probe:"))
    assert lines[probe_at + 1].startswith("  events:")
    for event in expected_bot_events():
        assert event in lines[probe_at + 1]
    assert "not verifiable" in out and "mention" in out
    assert "supersecret" not in out


def test_status_probe_that_cannot_run_still_names_the_expected_events(
    tmp_path, monkeypatch, capsys
):
    """R2.1 fail-closed: no token means no scope probe, but the manifest is
    local — the expected events and the caveat print anyway, never an "ok"."""
    monkeypatch.delenv(DEFAULT_BOT_TOKEN_ENV, raising=False)
    out = run_status(tmp_path, monkeypatch, capsys, cli_config(tmp_path), "--probe")
    assert "not probed" in out
    assert "events:" in out and "app_mention" in out and "not verifiable" in out


# -- R2.2: the heartbeat --------------------------------------------------------------


def test_a_heartbeat_is_recognised_only_when_bot_posted_and_well_formed():
    """The listener's recogniser: a member typing the marker is an ordinary
    message (no forged receipt, no hidden message), and only the fixed format
    with a hex nonce counts."""
    nonce = "0123abcd0123abcd"
    text = heartbeat_text(nonce)
    assert text == f"{HEARTBEAT_MARKER} {nonce}"
    assert heartbeat_nonce({"type": "message", "bot_id": "B1", "text": text}) == nonce
    assert heartbeat_nonce({"type": "message", "subtype": "bot_message", "text": text}) == nonce
    assert heartbeat_nonce({"type": "message", "user": "UHUMAN", "text": text}) == ""
    assert heartbeat_nonce({"type": "message", "bot_id": "B1", "text": f"{HEARTBEAT_MARKER} rm -rf"}) == ""
    assert heartbeat_nonce({"type": "message", "bot_id": "B1", "text": "hello"}) == ""


def test_every_heartbeat_echoed_over_the_doctors_own_connection_reads_ok_as_evidence(
    tmp_path, tokens
):
    """
    Feature: the deployment can diagnose itself
      Scenario: no listener runs here, every heartbeat comes back
        Given no Socket Mode listener holds this instance's lock
        When the doctor posts three heartbeats and all three reach its own connection
        Then the verdict is ok, the receiver is the doctor
         And the text still calls it evidence, not proof
         And every heartbeat is deleted again and only its own envelopes were acknowledged

    Requirement: docs/specs/issue-393/requirements.md R2.2
    """
    client = FakeDoctorClient()

    def socket_factory(app_token, web_client):
        client.socket = FakeSocket(app_token, web_client)
        return client.socket

    result = probe_second_consumer(
        cli_config(tmp_path),
        beats=3,
        window_seconds=0.5,
        client_factory=lambda token: client,
        socket_client_factory=socket_factory,
        listener_running=False,
    )
    assert result["verdict"] == "ok"
    assert result["receiver"] == "doctor"
    assert (result["echoed"], result["beats"]) == (3, 3)
    text = consumer_verdict_text(result)
    assert "3/3" in text and "not proof" in text
    assert client.deleted == [row["ts"] for row in client.posted]
    assert client.socket.connected and client.socket.closed
    assert len(client.socket.acks) == 3
    # The heartbeat is a marker and a nonce — never config content, never a token.
    for row in client.posted:
        assert row["text"].startswith(HEARTBEAT_MARKER + " ")
        assert "supersecret" not in row["text"] and "octocat" not in row["text"]


def test_a_missing_echo_is_evidence_of_a_second_consumer(tmp_path, tokens):
    """
    Feature: the deployment can diagnose itself
      Scenario: a second consumer takes some of the heartbeats
        Given another Socket Mode connection receives every other event
        When the doctor posts three heartbeats
        Then the verdict is split-suspected with the count that came back
         And the text names the split (events shared across connections, halving inbound)
         And calls itself evidence, not proof, and names the remedy

    Requirement: docs/specs/issue-393/requirements.md R2.2
    """
    client = FakeDoctorClient(echo=lambda index: index % 2 == 0)

    def socket_factory(app_token, web_client):
        client.socket = FakeSocket(app_token, web_client)
        return client.socket

    result = probe_second_consumer(
        cli_config(tmp_path),
        beats=3,
        window_seconds=0.3,
        client_factory=lambda token: client,
        socket_client_factory=socket_factory,
        listener_running=False,
    )
    assert result["verdict"] == "split-suspected"
    assert result["echoed"] == 2
    text = consumer_verdict_text(result)
    assert "2/3" in text
    assert "another Socket Mode consumer may hold" in text
    assert "splits" in text and "halving" in text
    assert "not proof" in text
    assert client.deleted == [row["ts"] for row in client.posted]


def test_with_a_running_listener_the_echo_is_read_from_its_event_log(tmp_path, tokens):
    """
    Feature: the deployment can diagnose itself
      Scenario: the instance's own listener is the receiver
        Given this instance's Socket Mode listener holds its lock
        When the doctor posts heartbeats and the listener records each receipt
        Then the doctor opens no connection of its own
         And reads the receipts back from the event log written after the probe began

    Requirement: docs/specs/issue-393/requirements.md R2.2
    """
    log = tmp_path / "events.jsonl"
    # A stale receipt from an earlier run must not count: same nonce shape,
    # written before the probe began.
    log.write_text(
        json.dumps({"event": "channel.heartbeat", "nonce": "deadbeefdeadbeef"}) + "\n"
    )
    client = FakeDoctorClient(log_path=log)
    opened = []
    nonces = iter(["deadbeefdeadbeef", "0000000000000001", "0000000000000002"])
    result = probe_second_consumer(
        cli_config(tmp_path),
        beats=3,
        window_seconds=0.5,
        client_factory=lambda token: client,
        socket_client_factory=lambda app, web: opened.append(app),
        listener_running=True,
        log_path=str(log),
        nonce_factory=lambda: next(nonces),
    )
    assert result["verdict"] == "ok" and result["receiver"] == "listener"
    assert result["echoed"] == 3
    assert opened == []  # never a second connection beside the listener


def test_a_listener_that_records_nothing_reads_as_a_suspected_split(tmp_path, tokens):
    """The listener mode's shortfall: nothing written to the log within the
    window is the same evidence, and the text adds the old-build remedy."""
    log = tmp_path / "events.jsonl"
    client = FakeDoctorClient(echo=lambda index: False, log_path=log)
    result = probe_second_consumer(
        cli_config(tmp_path),
        beats=2,
        window_seconds=0.2,
        client_factory=lambda token: client,
        listener_running=True,
        log_path=str(log),
    )
    assert result["verdict"] == "split-suspected" and result["echoed"] == 0
    assert "restart" in consumer_verdict_text(result)


@pytest.mark.parametrize(
    "setup,expected",
    [
        ("disabled", "not enabled"),
        ("no-bot-token", DEFAULT_BOT_TOKEN_ENV),
        ("no-channel", "channels.slack.channel"),
        ("no-app-token-no-listener", DEFAULT_APP_TOKEN_ENV),
        ("listener-but-log-off", "eventLog.enabled"),
        ("api-error", "boom"),
    ],
)
def test_a_probe_that_cannot_run_is_unverifiable_never_ok(
    tmp_path, monkeypatch, tokens, setup, expected
):
    """Fail-closed (design §Security): whatever stops the probe, the verdict is
    unverifiable with the reason — never a raise, never an ok."""
    config = cli_config(tmp_path)
    client = FakeDoctorClient()
    listener_running = False
    if setup == "disabled":
        config["channels"]["slack"]["enabled"] = False
    elif setup == "no-bot-token":
        monkeypatch.delenv(DEFAULT_BOT_TOKEN_ENV, raising=False)
    elif setup == "no-channel":
        config["channels"]["slack"]["channel"] = ""
    elif setup == "no-app-token-no-listener":
        monkeypatch.delenv(DEFAULT_APP_TOKEN_ENV, raising=False)
    elif setup == "listener-but-log-off":
        config["eventLog"] = {"enabled": False}
        listener_running = True
    else:

        def explode(**kwargs):
            raise RuntimeError("boom")

        client.chat_postMessage = explode  # type: ignore[method-assign]
    result = probe_second_consumer(
        config,
        beats=1,
        window_seconds=0.1,
        client_factory=lambda token: client,
        socket_client_factory=lambda app, web: FakeSocket(app, web),
        listener_running=listener_running,
    )
    assert result["verdict"] == "unverifiable"
    assert expected in result["reason"]
    assert "unverifiable" in consumer_verdict_text(result)
    assert "supersecret" not in json.dumps(result)


def test_the_listener_records_a_heartbeat_and_never_reads_it_as_input(
    tmp_path, monkeypatch, tokens
):
    """
    Feature: the deployment can diagnose itself
      Scenario: the running listener hears the doctor's heartbeat
        Given the Socket Mode listener is running with the event log on
        When Slack delivers the bot's own heartbeat message
        Then the listener acknowledges it and records a channel.heartbeat with the nonce
         And the inbound pipeline never sees it

    Requirement: docs/specs/issue-393/requirements.md R2.2
    """
    from the_loop.channels import inbound

    sockets = []

    class Socket(FakeSocket):
        def __init__(self, app_token=None, web_client=None):
            super().__init__(app_token, web_client)
            sockets.append(self)

    monkeypatch.setattr("slack_sdk.socket_mode.SocketModeClient", Socket, raising=False)
    monkeypatch.setattr(slack_mod, "build_client", lambda token: FakeDoctorClient())
    handled = []
    monkeypatch.setattr(
        inbound, "handle_socket_event", lambda *a, **k: handled.append(a) or {}
    )
    monkeypatch.setattr(slack_mod, "catch_up", lambda config: {"replies": 0})
    log = tmp_path / "events.jsonl"
    eventlog.configure("test", path=log)
    try:
        stop = threading.Event()
        config = cli_config(tmp_path)
        thread = threading.Thread(
            target=lambda: slack_mod.run_socket_listener(config, stop), daemon=True
        )
        thread.start()
        deadline = time.monotonic() + 5
        while not sockets and time.monotonic() < deadline:
            time.sleep(0.01)
        assert sockets, "the listener never connected"
        socket = sockets[0]
        socket.deliver(
            {
                "type": "message",
                "bot_id": "B0BOT",
                "channel": "C0CENTRAL",
                "text": heartbeat_text("abcdef0123456789"),
                "ts": "1700000000.000001",
            }
        )
        stop.set()
        thread.join(timeout=5)
    finally:
        eventlog.reset()
    records = list(eventlog.read_events(log, types=["channel.heartbeat"]))
    assert len(records) == 1
    assert records[0]["nonce"] == "abcdef0123456789"
    assert records[0]["channel_id"] == "C0CENTRAL"
    assert len(socket.acks) == 1
    assert handled == []
    assert "channel.heartbeat" in eventlog.EVENT_TYPES


# -- R2.3: declared channels against the directory --------------------------------------


class FakeDirectoryClient:
    """Membership + a workspace listing that either exhausts or never does."""

    def __init__(self, memberships=None, workspace=None, cap_pages=None, fail=False):
        self.memberships = memberships if memberships is not None else [
            {"id": "C0CENTRAL", "name": "the-loop"},
            {"id": "GTEST", "name": "test-room"},
        ]
        self.workspace = workspace or []
        self.cap_pages = cap_pages
        self.fail = fail

    def users_conversations(self, *, types, exclude_archived, limit, cursor=None):
        if self.fail:
            raise RuntimeError("missing_scope")
        return {"channels": list(self.memberships), "response_metadata": {}}

    def conversations_list(self, *, types, exclude_archived, limit, cursor=None):
        if self.fail:
            raise RuntimeError("missing_scope")
        page = int(cursor or 0)
        if self.cap_pages is not None:
            return {
                "channels": list(self.workspace),
                "response_metadata": {"next_cursor": str(page + 1)},
            }
        return {
            "channels": list(self.workspace) if page == 0 else [],
            "response_metadata": {"next_cursor": ""},
        }


def declare(tmp_path, config, target, work_item="github:octocat/hello-world#12"):
    """Declare ``target`` as ``work_item``'s room through the real store.

    An **id**, always: the store refuses a name ("resolve it before declaring
    it", issue-375) — so a declared room can only ever be *absent* from the
    directory, and the name-miss case belongs to ``channels.slack.channel``.
    """
    from the_loop.workchannels import CollaborationChannelStore

    CollaborationChannelStore(Path(config["state"]["root"]) / "portable").add(
        work_item, f"slack@{target}", actor="octocat", source="cli"
    )


def _rows(report):
    return {row["declared"]: row["status"] for row in report["channels"]}


def test_declared_channels_that_resolve_are_ok(tmp_path, tokens):
    """R2.3: the central channel by name and a declared room by id, both found."""
    config = cli_config(tmp_path, channel="#the-loop")
    declare(tmp_path, config, "GTEST")
    client = FakeDirectoryClient()
    report = check_declared_channels(config, client_factory=lambda token: client)
    assert _rows(report) == {"#the-loop": "ok", "GTEST": "ok"}
    by_declared = {row["declared"]: row for row in report["channels"]}
    assert by_declared["#the-loop"]["id"] == "C0CENTRAL"
    assert by_declared["GTEST"]["owner"] == "declared by github:octocat/hello-world#12"
    assert report["truncated"] is False


def test_a_declared_room_the_directory_does_not_hold_is_reported(tmp_path, tokens):
    """
    Feature: the deployment can diagnose itself
      Scenario: a declared room is absent from the bot's directory (B1)
        Given the central channel is declared by a name the directory does not hold
          And a work item declares a room by an id the directory never lists
        When the doctor checks the declared channels
        Then the name is a miss and the id is absent, each with what declared it
         And the rooms that do resolve are still reported ok

    Requirement: docs/specs/issue-393/requirements.md R2.3
    """
    config = cli_config(tmp_path, channel="#nowhere")
    declare(tmp_path, config, "GTEST")
    declare(tmp_path, config, "G0NOWHERE", work_item="github:octocat/hello-world#13")
    client = FakeDirectoryClient()
    report = check_declared_channels(config, client_factory=lambda token: client)
    assert _rows(report) == {"#nowhere": "miss", "G0NOWHERE": "absent", "GTEST": "ok"}
    by_declared = {row["declared"]: row for row in report["channels"]}
    assert by_declared["#nowhere"]["owner"] == "channels.slack.channel"
    assert by_declared["G0NOWHERE"]["owner"] == "declared by github:octocat/hello-world#13"
    assert report["truncated"] is False


def test_a_miss_over_a_truncated_listing_says_so(tmp_path, tokens):
    """R2.3 + R1.4: a name missing from a listing the page cap cut short is not a
    definitive miss — the report carries the truncation."""
    config = cli_config(tmp_path, channel="#nowhere")
    client = FakeDirectoryClient(workspace=[{"id": "CPUB", "name": "general"}], cap_pages=1)
    report = check_declared_channels(config, client_factory=lambda token: client)
    assert list(_rows(report).values()) == ["miss"]
    assert report["truncated"] is True


def test_a_declared_id_the_directory_does_not_list_is_absent(tmp_path, tokens):
    """R2.3: an id needs no lookup to be posted to, which is exactly why a
    directory that never lists it is worth a line — the bot is not in it."""
    config = cli_config(tmp_path, channel="C0ELSEWHERE")
    client = FakeDirectoryClient()
    report = check_declared_channels(config, client_factory=lambda token: client)
    assert _rows(report) == {"C0ELSEWHERE": "absent"}


def test_an_unreadable_directory_is_unverifiable_not_a_miss(tmp_path, tokens):
    """Fail-closed: when no listing can be read at all, a name is not "missing"
    — it is unverifiable, and the report says why nothing could be checked."""
    config = cli_config(tmp_path, channel="#test-room")
    client = FakeDirectoryClient(fail=True)
    report = check_declared_channels(config, client_factory=lambda token: client)
    assert list(_rows(report).values()) == ["unverifiable"]


def test_no_bot_token_makes_every_declared_channel_unverifiable(tmp_path, monkeypatch):
    monkeypatch.delenv(DEFAULT_BOT_TOKEN_ENV, raising=False)
    report = check_declared_channels(cli_config(tmp_path))
    assert DEFAULT_BOT_TOKEN_ENV in report["reason"]
    assert list(_rows(report).values()) == ["unverifiable"]


def test_nothing_declared_is_said_not_crashed(tmp_path, tokens):
    report = check_declared_channels(cli_config(tmp_path, channel=""))
    assert report["channels"] == [] and "nothing declared" in report["reason"]


def test_conversation_known_is_tri_state(tmp_path, monkeypatch):
    """The directory's new question, all three answers: listed, absent from a
    listing that was read, and no listing readable at all."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    listed = SlackDirectory(
        path=tmp_path / "a" / "slack-directory.json",
        token_env=DEFAULT_BOT_TOKEN_ENV,
        client_factory=lambda token: FakeDirectoryClient(),
    )
    assert listed.conversation_known("GTEST") is True
    assert listed.conversation_known("C0ELSEWHERE") is False
    assert listed.has_conversations() is True
    unreadable = SlackDirectory(
        path=tmp_path / "b" / "slack-directory.json",
        token_env=DEFAULT_BOT_TOKEN_ENV,
        client_factory=lambda token: FakeDirectoryClient(fail=True),
    )
    assert unreadable.conversation_known("GTEST") is None
    assert unreadable.has_conversations() is False
    assert listed.conversation_known("not-an-id") is False


# -- the command ----------------------------------------------------------------------


def run_doctor(tmp_path, monkeypatch, capsys, config, *argv):
    from the_loop.commands.diagnose_cmd import DoctorCommand

    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    (tmp_path / "cli-config.yaml").write_text(json.dumps(config), encoding="utf-8")
    parser = argparse.ArgumentParser()
    DoctorCommand().add_arguments(parser)
    code = DoctorCommand().run(parser.parse_args(["slack", *argv]))
    return code, capsys.readouterr().out


def test_doctor_is_registered_as_a_command():
    from the_loop.commands import iter_commands

    assert "doctor" in {command.name for command in iter_commands()}


def test_doctor_slack_prints_all_three_sections_and_exits_zero_when_clean(
    tmp_path, monkeypatch, capsys, tokens
):
    """
    Feature: the deployment can diagnose itself
      Scenario: a healthy deployment reads clean
        Given the app holds its scopes, every declared channel resolves
          And every heartbeat comes back
        When `the-loop doctor slack` runs
        Then it prints the app, channels and consumers sections
         And the events line carries the unverifiability caveat
         And it exits 0 without printing a token

    Requirement: docs/specs/issue-393/requirements.md R2.1, R2.2, R2.3
    """
    config = cli_config(tmp_path, channel="#the-loop")
    declare(tmp_path, config, "GTEST")
    client = FakeDoctorClient()
    client.auth_test = lambda: FakeResponse(  # type: ignore[method-assign]
        {"ok": True},
        "chat:write,groups:history,app_mentions:read",
    )

    def socket_factory(app_token, web_client):
        client.socket = FakeSocket(app_token, web_client)
        return client.socket

    monkeypatch.setattr(slack_mod, "build_client", lambda token: client)
    monkeypatch.setattr(doctor_mod, "_default_socket_client", socket_factory)
    monkeypatch.setattr(doctor_mod, "listener_is_running", lambda config: False)
    code, out = run_doctor(tmp_path, monkeypatch, capsys, config, "--window", "0.5")
    assert code == 0, out
    assert "app:" in out and "channels:" in out and "consumers:" in out
    assert "events:" in out and "not verifiable" in out
    assert "[ok] 3/3 heartbeats" in out and "not proof" in out
    assert "[ok] #the-loop → C0CENTRAL" in out
    assert "[ok] GTEST — listed in the bot's directory (declared by github:octocat/hello-world#12)" in out
    assert "[!]" not in out
    assert "supersecret" not in out


def test_doctor_slack_exits_one_on_a_miss_or_a_suspected_split(
    tmp_path, monkeypatch, capsys, tokens
):
    """A finding costs the exit code — the bring-up step "confirm `doctor slack`
    is green" needs a code, not a read."""
    config = cli_config(tmp_path)  # a central channel the heartbeat CAN be posted to
    declare(tmp_path, config, "G0NOWHERE")
    client = FakeDoctorClient(echo=lambda index: index == 0)
    client.auth_test = lambda: FakeResponse(  # type: ignore[method-assign]
        {"ok": True},
        "chat:write,groups:history,app_mentions:read",
    )

    def socket_factory(app_token, web_client):
        client.socket = FakeSocket(app_token, web_client)
        return client.socket

    monkeypatch.setattr(slack_mod, "build_client", lambda token: client)
    monkeypatch.setattr(doctor_mod, "_default_socket_client", socket_factory)
    monkeypatch.setattr(doctor_mod, "listener_is_running", lambda config: False)
    code, out = run_doctor(tmp_path, monkeypatch, capsys, config, "--window", "0.3")
    assert code == 1
    assert "[!] G0NOWHERE — declared by id but absent" in out
    assert "[!] 1/3 heartbeats" in out
    assert "another Socket Mode consumer may hold" in out


def test_doctor_slack_never_crashes_and_never_says_ok_for_what_it_could_not_measure(
    tmp_path, monkeypatch, capsys
):
    """No tokens at all: every section prints an unverifiable line, the command
    exits 0 (nothing was FOUND) and no probe raised."""
    monkeypatch.delenv(DEFAULT_BOT_TOKEN_ENV, raising=False)
    monkeypatch.delenv(DEFAULT_APP_TOKEN_ENV, raising=False)
    code, out = run_doctor(tmp_path, monkeypatch, capsys, cli_config(tmp_path))
    assert code == 0
    assert "not probed" in out
    assert "unverifiable" in out
    assert "[ok]" not in out


def test_no_heartbeat_posts_nothing(tmp_path, monkeypatch, capsys, tokens):
    client = FakeDoctorClient()
    monkeypatch.setattr(slack_mod, "build_client", lambda token: client)
    code, out = run_doctor(tmp_path, monkeypatch, capsys, cli_config(tmp_path), "--no-heartbeat")
    assert client.posted == []
    assert "skipped (--no-heartbeat)" in out
    assert code in (0, 1)
