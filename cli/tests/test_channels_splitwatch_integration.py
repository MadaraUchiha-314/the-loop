"""Integration scenarios for issue-413: the split check inside the listener, and
the surfaces that report it.

The listener is run for real — its connect, its heartbeat branch, its reconcile
deadline and its shutdown — with only the process boundaries faked: the Socket
Mode client (monkeypatched on ``slack_sdk``) and the Web client (the injected
``build_client``), which stands in for Slack by handing a posted heartbeat back
over the socket exactly when the scenario says this instance won the toss.

The status scenarios drive the real renderers over a real state file, because the
defect being fixed is precisely that a finding reached no surface.

Spec: docs/specs/issue-413/{bugfix,design,testing-plan}.md, T6/T7/T9.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from the_loop import eventlog
from the_loop.channels import commands as channel_commands
from the_loop.channels import slack as slack_mod
from the_loop.channels import splitwatch
from the_loop.channels.slack import (
    DEFAULT_APP_TOKEN_ENV,
    DEFAULT_BOT_TOKEN_ENV,
    SPLIT_CAVEAT,
    SPLIT_REMEDY,
)
from the_loop.commands import channels_cmd
from the_loop.core import lifecycle as core_lifecycle

CHANNEL = "C0CENTRAL"


# -- the process boundaries ----------------------------------------------------------


class FakeRequest:
    def __init__(self, type_, payload):
        self.type = type_
        self.payload = payload
        self.envelope_id = "env-1"


class FakeSocketModeClient:
    """Enough of ``SocketModeClient`` to drive the listener from a test."""

    instances: list = []

    def __init__(self, app_token=None, web_client=None):
        self.app_token = app_token
        self.web_client = web_client
        self.socket_mode_request_listeners = []
        self.connected = False
        self.closed = False
        self.acks = []
        FakeSocketModeClient.instances.append(self)

    def connect(self):
        self.connected = True

    def close(self):
        self.closed = True

    def send_socket_mode_response(self, response):
        self.acks.append(response)

    def deliver(self, type_, payload):
        for listener in list(self.socket_mode_request_listeners):
            listener(self, FakeRequest(type_, payload))


class FakeWebClient:
    """Slack, as far as the split check is concerned: it takes the heartbeat and
    decides — per beat — whether this instance or the phantom receives it."""

    def __init__(self, echo=lambda index: True):
        self.echo = echo
        self.posted = []
        self.deleted = []

    def chat_postMessage(self, *, channel, text):
        index = len(self.posted)
        ts = f"1700000000.{index:06d}"
        self.posted.append({"channel": channel, "text": text, "ts": ts})
        if self.echo(index) and FakeSocketModeClient.instances:
            FakeSocketModeClient.instances[0].deliver(
                "events_api",
                {
                    "event": {
                        "type": "message",
                        "bot_id": "B0BOT",
                        "channel": channel,
                        "text": text,
                        "ts": ts,
                    }
                },
            )
        return {"ok": True, "ts": ts}

    def chat_delete(self, *, channel, ts):
        self.deleted.append({"channel": channel, "ts": ts})
        return {"ok": True}

    def conversations_info(self, *, channel):
        return {"ok": True, "channel": {"id": channel, "is_channel": True}}

    def auth_test(self):
        return type("Response", (dict,), {"headers": {"x-oauth-scopes": "chat:write"}})(
            {"ok": True, "user_id": "UBOT"}
        )


@pytest.fixture
def listener_env(tmp_path, monkeypatch):
    """A socket-mode channel with both tokens and the two clients faked."""
    FakeSocketModeClient.instances.clear()
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-SECRETBOT")
    monkeypatch.setenv(DEFAULT_APP_TOKEN_ENV, "xapp-SECRETAPP")
    monkeypatch.setattr(
        "slack_sdk.socket_mode.SocketModeClient", FakeSocketModeClient, raising=False
    )
    monkeypatch.setattr(slack_mod, "catch_up", lambda config: {"replies": 0})
    # A short window: only a check that is SHORT ever waits it out, and no test
    # should pay five real seconds to watch an absence.
    monkeypatch.setattr(splitwatch, "DEFAULT_WINDOW_SECONDS", 0.2)
    eventlog.configure("channels", path=tmp_path / "events.jsonl", enabled=True)

    def make(echo=lambda index: True, **read):
        client = FakeWebClient(echo=echo)
        monkeypatch.setattr(slack_mod, "build_client", lambda token: client)
        config = {
            "state": {"root": str(tmp_path / "state")},
            "eventLog": {"enabled": True, "path": str(tmp_path / "events.jsonl")},
            "routing": {"authorizedUsers": [{"github": "gh-U", "slack": "UHUMAN"}]},
            "channels": {
                "slack": {
                    "enabled": True,
                    "channel": CHANNEL,
                    "publish": ["gate.feedback"],
                    "read": {"mode": "socket", **read},
                }
            },
        }
        return config, client

    yield make
    eventlog.reset()


def run_listener(config, stop, **kwargs):
    """Start the listener on its own thread; hand back (thread, socket, result)."""
    result = {}
    thread = threading.Thread(
        target=lambda: result.update(
            code=slack_mod.run_socket_listener(config, stop, **kwargs)
        ),
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + 5
    while not FakeSocketModeClient.instances and time.monotonic() < deadline:
        time.sleep(0.01)
    assert FakeSocketModeClient.instances, "the listener never connected"
    return thread, FakeSocketModeClient.instances[0], result


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def state_of(config):
    return splitwatch.read_state(splitwatch.split_state_path(config))


def events_in(config):
    path = Path(config["eventLog"]["path"])
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# -- T6: the listener checks itself --------------------------------------------------


class TestTheListenerChecksItself:
    def test_one_check_runs_at_connect(self, listener_env):
        """Scenario: the listener measures its own share before it idles

        Given a Socket Mode listener with the split check at its default
        When the listener connects and finishes its catch-up read
        Then it posts its heartbeats, hears them back over its own connection,
          and records a clean check
        And every heartbeat it posted is deleted again

        Requirement: docs/specs/issue-413/bugfix.md R1.1, R1.4
        """
        config, client = listener_env()
        stop = threading.Event()
        thread, _socket, _result = run_listener(config, stop, catch_up_override=0)
        assert wait_for(lambda: state_of(config) is not None)
        stop.set()
        thread.join(timeout=5)
        state = state_of(config)
        assert state is not None
        assert (state.verdict, state.beats, state.echoed) == ("ok", 2, 2)
        assert len(client.posted) == 2
        assert [d["ts"] for d in client.deleted] == [p["ts"] for p in client.posted]

    def test_a_phantom_consumer_is_found_without_anyone_asking(self, listener_env):
        """Scenario: half the heartbeats land somewhere else

        Given a second Socket Mode consumer holding the same app-level token
        When Slack routes one of the listener's own heartbeats to it
        Then the listener records `split-suspected` and emits a warning naming
          the remedy — with no operator having run anything

        Requirement: docs/specs/issue-413/bugfix.md R1.1, R2.1, R4.1
        """
        config, _client = listener_env(echo=lambda index: index == 0)
        stop = threading.Event()
        thread, _socket, _result = run_listener(config, stop, catch_up_override=0)
        assert wait_for(lambda: state_of(config) is not None)
        stop.set()
        thread.join(timeout=5)
        state = state_of(config)
        assert state is not None
        assert (state.verdict, state.echoed) == ("split-suspected", 1)
        warned = [
            e for e in events_in(config) if e["event"] == "channel.split_suspected"
        ]
        assert len(warned) == 1
        assert warned[0]["level"] == "warning"
        assert warned[0]["remedy"] == SPLIT_REMEDY

    def test_the_reconcile_deadline_carries_the_check(self, listener_env):
        """Scenario: the check keeps running for as long as the listener does

        Given `read.catchUpSeconds` reached while the listener idles
        When the reconcile cycle runs
        Then a split check runs beside it, on the same deadline

        Requirement: docs/specs/issue-413/bugfix.md R1.2
        """
        config, client = listener_env()
        stop = threading.Event()
        thread, _socket, _result = run_listener(config, stop, catch_up_override=0.05)
        assert wait_for(lambda: len(client.posted) >= 6)
        stop.set()
        thread.join(timeout=5)
        state = state_of(config)
        assert state is not None
        assert state.checks >= 3

    def test_connect_only_means_connect_only(self, listener_env):
        """Scenario: `read.catchUpSeconds: 0` keeps its contract for both cycles

        Requirement: docs/specs/issue-413/bugfix.md R1.3
        """
        config, client = listener_env(catchUpSeconds=0)
        stop = threading.Event()
        thread, _socket, _result = run_listener(config, stop)
        assert wait_for(lambda: state_of(config) is not None)
        time.sleep(0.3)
        stop.set()
        thread.join(timeout=5)
        assert len(client.posted) == 2
        state = state_of(config)
        assert state is not None
        assert state.checks == 1

    def test_the_check_can_be_turned_off_entirely(self, listener_env):
        """Scenario: a room that must stay quiet

        Requirement: docs/specs/issue-413/bugfix.md R1.5
        """
        config, client = listener_env(splitCheckBeats=0)
        stop = threading.Event()
        thread, _socket, _result = run_listener(config, stop, catch_up_override=0.05)
        time.sleep(0.3)
        stop.set()
        thread.join(timeout=5)
        assert client.posted == []
        assert state_of(config) is None

    def test_the_doctors_receipt_is_still_written(self, listener_env):
        """Scenario: `doctor slack` keeps working

        Given the doctor posts a heartbeat while this listener runs
        When the listener receives it
        Then it is still recorded as `channel.heartbeat`, which is what the
          doctor reads back, as well as reaching the listener's own check

        Requirement: docs/specs/issue-413/bugfix.md R1.4 / design § Overview
        """
        config, _client = listener_env()
        stop = threading.Event()
        thread, socket, _result = run_listener(config, stop, catch_up_override=0)
        assert wait_for(lambda: state_of(config) is not None)
        socket.deliver(
            "events_api",
            {
                "event": {
                    "type": "message",
                    "bot_id": "B0BOT",
                    "channel": CHANNEL,
                    "text": slack_mod.heartbeat_text("deadbeefdeadbeef"),
                    "ts": "1700000009.000000",
                }
            },
        )
        stop.set()
        thread.join(timeout=5)
        receipts = [e for e in events_in(config) if e["event"] == "channel.heartbeat"]
        assert any(r["nonce"] == "deadbeefdeadbeef" for r in receipts)

    def test_a_check_that_raises_never_ends_the_listener(self, listener_env):
        """Scenario: a diagnostic is not allowed to take the listener with it

        Requirement: docs/specs/issue-413/bugfix.md R1.7
        """
        config, _client = listener_env()
        original = splitwatch.SplitWatch.run_cycle

        def boom(self, stop_event=None):
            raise RuntimeError("the diagnostic exploded")

        splitwatch.SplitWatch.run_cycle = boom
        try:
            stop = threading.Event()
            thread, socket, result = run_listener(config, stop, catch_up_override=0)
            # Still serving envelopes after the explosion.
            socket.deliver("events_api", {"event": {"type": "unknown"}})
            stop.set()
            thread.join(timeout=5)
        finally:
            splitwatch.SplitWatch.run_cycle = original
        assert result.get("code") == 0
        assert socket.closed


# -- T7: the surfaces ----------------------------------------------------------------


def write_state(tmp_path, **fields) -> dict:
    """A recorded check, as the listener would have left it."""
    config: dict = {"state": {"root": str(tmp_path / "state")}}
    path = Path(splitwatch.split_state_path(config))
    path.parent.mkdir(parents=True, exist_ok=True)
    base = {
        "verdict": "split-suspected",
        "checkedAt": "2026-09-21T07:41:02Z",
        "beats": 2,
        "echoed": 1,
        "windowSeconds": 5.0,
        "channel": CHANNEL,
        "reason": "",
        "checks": 12,
        "short": 5,
        "consecutiveShort": 1,
        "recent": ["ok", "split-suspected", "ok", "split-suspected"],
        "intervalSeconds": 900,
    }
    base.update(fields)
    path.write_text(json.dumps(base), encoding="utf-8")
    return config


class TestStatusReportsIt:
    def test_status_carries_the_finding(self, tmp_path):
        """R3.1, R3.3, R3.6 — the operator learns it from the command they were
        already running, and the document carries the same facts."""
        config = write_state(tmp_path)
        doc = core_lifecycle.status_all(config)
        assert doc["slackSplit"]["suspected"] is True
        assert doc["slackSplit"]["echoed"] == 1
        lines = core_lifecycle.split_lines(doc)
        assert "1/2 heartbeats reached the listener" in lines[0]
        # The window's own count, not the lifetime total: "5 of the last 4" is
        # the kind of line an operator stops trusting.
        assert "2 of the last 4 checks short" in lines[0]
        assert lines[1] == SPLIT_CAVEAT
        assert lines[2] == SPLIT_REMEDY

    def test_a_clean_deployment_gains_no_report(self, tmp_path):
        """R3.2 — which is what keeps the report worth reading when it appears."""
        config = write_state(tmp_path, verdict="ok", echoed=2, recent=["ok", "ok"])
        assert core_lifecycle.split_lines(core_lifecycle.status_all(config)) == []
        # And a deployment that never ran one says nothing at all.
        bare = {"state": {"root": str(tmp_path / "never")}}
        assert core_lifecycle.status_all(bare)["slackSplit"] == {}
        assert core_lifecycle.split_lines({"slackSplit": {}}) == []

    def test_a_split_never_moves_ok(self, tmp_path):
        """R3.7 — `ok` means every enabled service is RUNNING, and a listener
        hearing half of its traffic is running."""
        clean = write_state(tmp_path, verdict="ok", echoed=2, recent=["ok"])
        before = core_lifecycle.status_all(clean)["ok"]
        split = write_state(tmp_path)
        assert core_lifecycle.status_all(split)["ok"] is before

    def test_status_never_fails_on_an_unreadable_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            splitwatch, "read_state", lambda _p: (_ for _ in ()).throw(OSError("nope"))
        )
        assert core_lifecycle._slack_split({"state": {"root": str(tmp_path)}}) == {}

    def test_the_slash_command_says_the_same_thing(self, tmp_path):
        """R3.5 — the operator reading this in Slack is the one whose room is
        losing envelopes."""
        doc = core_lifecycle.status_all(write_state(tmp_path))
        rendered = channel_commands.render_status(doc)
        assert "• slack: inbound may be split" in rendered
        assert SPLIT_REMEDY in rendered
        # One bullet, not three: it is one finding with a caveat and a remedy.
        assert rendered.count("• slack:") == 1


class TestChannelsStatusReportsIt:
    def _output(self, capsys, config, probe=False):
        channels_cmd._status(config, probe=probe)
        return capsys.readouterr().out

    def test_a_suspected_split_is_a_finding(self, tmp_path, capsys):
        """R3.4 — `[!]`, the class `channels status` already uses for a finding."""
        config = write_state(tmp_path)
        config["channels"] = {
            "slack": {"enabled": True, "channel": CHANNEL, "read": {"mode": "socket"}}
        }
        out = self._output(capsys, config)
        assert "[!] inbound may be split" in out
        assert SPLIT_CAVEAT in out and SPLIT_REMEDY in out

    def test_a_clean_check_states_its_cadence(self, tmp_path, capsys):
        """R3.4 — an operator must be able to tell "measured and clean" from
        "never measured"."""
        config = write_state(tmp_path, verdict="ok", echoed=2, recent=["ok"])
        config["channels"] = {
            "slack": {"enabled": True, "channel": CHANNEL, "read": {"mode": "socket"}}
        }
        out = self._output(capsys, config)
        assert "split check:  2 heartbeat(s) every 900s" in out
        assert "2/2" in out and "1 retained, none short" in out
        assert "[!] inbound" not in out

    def test_poll_mode_has_no_listener_to_check(self, tmp_path, capsys):
        config = write_state(tmp_path)
        config["channels"] = {
            "slack": {"enabled": True, "channel": CHANNEL, "read": {"mode": "poll"}}
        }
        assert "split check:" not in self._output(capsys, config)


# -- T9: nothing a ticket should not carry -------------------------------------------


class TestSecretsAreNeverPrinted:
    @pytest.mark.parametrize("case", ["clean", "short", "unverifiable"])
    def test_no_token_reaches_any_sink(self, listener_env, tmp_path, capsys, case):
        """R2.6 / bugfix § Security — the state file, both event records and
        every rendered line, on all three paths."""
        echo = {"clean": (lambda i: True), "short": (lambda i: False)}.get(
            case, lambda i: True
        )
        config, client = listener_env(echo=echo)
        if case == "unverifiable":
            client.chat_postMessage = lambda **_: (_ for _ in ()).throw(
                RuntimeError("ratelimited")
            )
        stop = threading.Event()
        thread, _socket, _result = run_listener(config, stop, catch_up_override=0)
        assert wait_for(lambda: state_of(config) is not None)
        stop.set()
        thread.join(timeout=5)

        doc = core_lifecycle.status_all(config)
        channels_cmd._status(config)
        sinks = "\n".join(
            [
                Path(splitwatch.split_state_path(config)).read_text(encoding="utf-8"),
                "\n".join(json.dumps(e) for e in events_in(config)),
                json.dumps(doc["slackSplit"]),
                "\n".join(core_lifecycle.split_lines(doc)),
                channel_commands.render_status(doc),
                capsys.readouterr().out,
            ]
        )
        assert "SECRETBOT" not in sinks
        assert "SECRETAPP" not in sinks
        assert "xoxb-" not in sinks and "xapp-" not in sinks
