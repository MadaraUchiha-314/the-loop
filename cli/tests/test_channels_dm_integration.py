"""Integration scenarios for issue-362: the Socket Mode listener, end to end.

The listener is run for real — its connect, its filter, its reconcile deadline
and its shutdown — with only the process boundaries faked: the Socket Mode
client (monkeypatched on ``slack_sdk``), the Web client (the injected
``build_client``), and — where the scenario is about the listener rather than the
pipeline — ``handle_socket_event`` itself, since
``test_channels_integration.py`` already owns what it does with a message. The
allow-list scenario runs the real pipeline.

Spec: docs/specs/issue-362/{bugfix,design,testing-plan}.md.
"""

from __future__ import annotations

import logging
import threading
import time

import pytest

from the_loop.channels import slack as slack_mod
from the_loop.channels.slack import DEFAULT_APP_TOKEN_ENV, DEFAULT_BOT_TOKEN_ENV


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
        request = FakeRequest(type_, payload)
        for listener in self.socket_mode_request_listeners:
            listener(self, request)


class FakeWebClient:
    def __init__(self, info=None, scopes="chat:write,channels:history"):
        self._info = info if info is not None else {"id": "D0AU0SGP30T", "is_im": True}
        self._scopes = scopes

    def conversations_info(self, *, channel):
        return {"ok": True, "channel": self._info}

    def auth_test(self):
        response = dict(ok=True, user_id="UBOT")
        return type(
            "Response",
            (dict,),
            {"headers": {"x-oauth-scopes": self._scopes}},
        )(response)


@pytest.fixture
def listener_env(tmp_path, monkeypatch):
    """A socket-mode DM channel with both tokens, and the two clients faked."""
    FakeSocketModeClient.instances.clear()
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    monkeypatch.setenv(DEFAULT_APP_TOKEN_ENV, "xapp-test")
    monkeypatch.setattr(
        "slack_sdk.socket_mode.SocketModeClient", FakeSocketModeClient, raising=False
    )
    monkeypatch.setattr(slack_mod, "build_client", lambda token: FakeWebClient())
    return {
        "state": {"root": str(tmp_path / "state")},
        "routing": {"authorizedUsers": [{"github": "gh-UHUMAN", "slack": "UHUMAN"}]},
        "channels": {
            "slack": {
                "enabled": True,
                "channel": "D0AU0SGP30T",
                "publish": ["gate.feedback", "work-item.create"],
                "read": {"mode": "socket"},
            }
        },
    }


def run_listener(config, stop, **kwargs):
    """Start the listener on its own thread and hand back (thread, client)."""
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


def test_a_message_im_envelope_reaches_the_inbound_pipeline(
    listener_env, monkeypatch, tmp_path
):
    """Scenario: A message typed in a DM reaches the-loop in real time

    Given a socket-mode channel configured with a direct-message id
    And a Slack app subscribed to message.im
    When Slack delivers a message.im envelope over the Socket Mode connection
    Then the listener acknowledges it before handling it
    And the message reaches the inbound pipeline through the same filter a
      public-channel message takes, with no DM-specific branch

    Requirement: docs/specs/issue-362/bugfix.md R1.2
    """
    seen = []
    monkeypatch.setattr(
        "the_loop.channels.inbound.handle_socket_event",
        lambda event, config, **_kw: seen.append(event) or {"outcome": "processed"},
    )
    monkeypatch.setattr(slack_mod, "catch_up", lambda config: {"replies": 0})
    stop = threading.Event()
    thread, client, _ = run_listener(listener_env, stop)
    try:
        client.deliver(
            "events_api",
            {
                "event": {
                    "type": "message",
                    "channel": "D0AU0SGP30T",
                    "channel_type": "im",
                    "ts": "1800.1",
                    "user": "UHUMAN",
                    "text": "go with A",
                }
            },
        )
    finally:
        stop.set()
        thread.join(timeout=5)
    assert len(client.acks) == 1, "the envelope must be acknowledged first"
    assert [event["channel_type"] for event in seen] == ["im"]


def test_the_listener_warns_once_about_the_dm_subscription(
    listener_env, monkeypatch, caplog
):
    """Scenario: The listener says the app cannot receive this channel's events

    Given a socket-mode channel configured with a direct-message id
    And an app whose bot scopes do not include im:history
    When the listener connects
    Then it probes the installed app once and logs the finding as a warning
    And the finding names the channel, the missing scope and the missing event

    Requirement: docs/specs/issue-362/bugfix.md R2.4, R2.5
    """
    monkeypatch.setattr(slack_mod, "catch_up", lambda config: {"replies": 0})
    stop = threading.Event()
    with caplog.at_level(logging.WARNING, logger="the-loop.channels"):
        thread, _client, _ = run_listener(listener_env, stop)
        stop.set()
        thread.join(timeout=5)
    findings = [
        record for record in caplog.records if "D0AU0SGP30T" in record.getMessage()
    ]
    assert len(findings) == 1
    message = findings[0].getMessage()
    assert "im:history" in message and "message.im" in message


def test_a_probe_that_raises_never_keeps_the_listener_from_listening(
    listener_env, monkeypatch
):
    """Scenario: A failing diagnostic does not cost the channel its listener

    Given a socket-mode channel whose probe raises
    When the listener starts
    Then it connects, listens, and stops cleanly with exit code 0

    Requirement: docs/specs/issue-362/bugfix.md R2.4
    """

    def explode(config, **kwargs):
        raise RuntimeError("probe boom")

    monkeypatch.setattr(slack_mod, "probe_subscription", explode)
    monkeypatch.setattr(slack_mod, "catch_up", lambda config: {"replies": 0})
    stop = threading.Event()
    thread, client, result = run_listener(listener_env, stop)
    stop.set()
    thread.join(timeout=5)
    assert client.connected and client.closed
    assert result["code"] == 0


def test_the_listener_reconciles_on_its_deadline_and_survives_a_raising_cycle(
    listener_env, monkeypatch
):
    """Scenario: Socket mode re-reads the threads periodically

    Given a socket-mode channel with a reconcile interval
    When the listener runs for several intervals
    Then it runs one catch-up read at connect and one per interval after it
    And a cycle that raises does not stop the listener
    And the stop event ends the listener without waiting for the next interval

    Requirement: docs/specs/issue-362/bugfix.md R3.1, R3.3
    """
    cycles = []

    def flaky(config):
        cycles.append(time.monotonic())
        if len(cycles) == 2:
            raise RuntimeError("reconcile boom")
        return {"replies": 0}

    monkeypatch.setattr(slack_mod, "catch_up", flaky)
    stop = threading.Event()
    thread, _client, result = run_listener(listener_env, stop, catch_up_override=0.05)
    deadline = time.monotonic() + 5
    while len(cycles) < 4 and time.monotonic() < deadline:
        time.sleep(0.01)
    stopped_at = time.monotonic()
    stop.set()
    thread.join(timeout=5)
    assert not thread.is_alive(), "the stop event must end the listener promptly"
    assert time.monotonic() - stopped_at < 1.0
    assert len(cycles) >= 4, "the reconcile must keep running after a raising cycle"
    assert result["code"] == 0


def test_zero_disables_the_reconcile_and_keeps_the_connect_read(
    listener_env, monkeypatch
):
    """Scenario: An operator keeps 16.0.1's behaviour

    Given a socket-mode channel with read.catchUpSeconds set to 0
    When the listener runs for longer than any interval would be
    Then exactly one catch-up read happens, at connect

    Requirement: docs/specs/issue-362/bugfix.md R3.2
    """
    cycles = []
    monkeypatch.setattr(
        slack_mod, "catch_up", lambda config: cycles.append(1) or {"replies": 0}
    )
    listener_env["channels"]["slack"]["read"]["catchUpSeconds"] = 0
    stop = threading.Event()
    thread, _client, _ = run_listener(listener_env, stop)
    time.sleep(0.3)
    stop.set()
    thread.join(timeout=5)
    assert cycles == [1]


def test_an_unauthorized_dm_author_is_dropped(listener_env, monkeypatch, tmp_path):
    """Scenario: Subscribing to a DM's events grants nobody any authority

    Given a socket-mode direct-message channel with the work-item.create grant
    And a member who is not in routing.authorizedUsers
    When Slack delivers their top-level message.im envelope
    Then it is refused as unauthorized-actor
    And no issue is created and nothing is mirrored

    Requirement: docs/specs/issue-362/bugfix.md §AC2 — a new EVENT is not a new
    AUTHORITY. The allow-list sits above classification and is untouched here;
    this pins that a DM goes through it like any other conversation.
    """
    from the_loop.channels import inbound

    monkeypatch.setattr(
        "the_loop.comments.post_issue_comment_with_url",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not mirror")),
    )
    outcome = inbound.handle_socket_event(
        {
            "type": "message",
            "channel": "D0AU0SGP30T",
            "channel_type": "im",
            "ts": "1800.9",
            "user": "UEVIL",
            "text": "open an issue for me",
        },
        listener_env,
    )
    assert outcome.get("outcome") == "unauthorized-actor"
