"""Integration scenarios for the Slack adapters and the extracted classifier
(issue-496, T2/T7/T8 — R1.2, R2.4, R2.5, R2.7, R5.9, R7.2, R7.3; abuse case 2).

Feature: one Slack app serves every instance through the gateway
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from gateway_support import GatewayHarness
from the_loop.channels import slack as slack_mod
from the_loop.gateway.adapters.ingest import Ingest
from the_loop.gateway.adapters.slack_http import build_slack_http_router
from the_loop.gateway.adapters.slack_socket import SlackSocketAdapter

SIGNING = "slack-signing-secret"


class FakeRequest:
    def __init__(self, type_, payload, envelope_id="env-1"):
        self.type = type_
        self.payload = payload
        self.envelope_id = envelope_id


class FakeSocketModeClient:
    """Enough of ``SocketModeClient`` to drive the adapter; records, at ack time, how
    many events the store held — the store-before-ack proof."""

    def __init__(self, app_token=None, web_client=None, store=None):
        self.app_token = app_token
        self.socket_mode_request_listeners = []
        self.connected = False
        self.closed = False
        self.acks = []
        self.store = store

    def connect(self):
        self.connected = True

    def close(self):
        self.closed = True

    def send_socket_mode_response(self, response):
        held = sum(r.events for r in self.store.subjects()) if self.store else None
        self.acks.append(
            (
                getattr(response, "envelope_id", None) or response.get("envelope_id"),
                held,
            )
        )

    def deliver(self, type_, payload, envelope_id="env-1"):
        for listener in list(self.socket_mode_request_listeners):
            listener(self, FakeRequest(type_, payload, envelope_id))


class FakeWatch:
    def __init__(self):
        self.seen = []

    def observe(self, nonce):
        self.seen.append(nonce)


@pytest.fixture()
def gw(tmp_path, monkeypatch):
    monkeypatch.setenv("THE_LOOP_SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.setenv("THE_LOOP_SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", SIGNING)
    harness = GatewayHarness(
        tmp_path,
        slack={
            "socket": {"enabled": True},
            "http": {"enabled": True},
            "rooms": [{"channel": "CROOM", "workItem": "github:o/r#14"}],
        },
    )
    ingest = Ingest(harness.state)
    harness.watch = FakeWatch()
    harness.socket = SlackSocketAdapter(
        ingest,
        harness.config,
        client_factory=lambda app_token, web_client: FakeSocketModeClient(
            app_token, web_client, store=harness.store
        ),
        web_client_factory=lambda token: None,
        watch=harness.watch,
    )
    assert harness.socket.start()
    harness.app.include_router(build_slack_http_router(ingest, harness.config))
    yield harness
    harness.socket.stop()
    harness.close()


def _message(
    channel="CROOM", ts="1700.5", thread=None, user="U1", event_id="Ev01", **event
):
    body = {
        "type": "message",
        "channel": channel,
        "ts": ts,
        "user": user,
        "text": "approved",
        **event,
    }
    if thread:
        body["thread_ts"] = thread
    return {"event_id": event_id, "team_id": "T1", "event": body}


def test_a_slack_envelope_is_stored_before_it_is_acknowledged(gw):
    """
    Feature: one Slack app serves every instance through the gateway
      Scenario: a Slack envelope is stored before it is acknowledged
        Given laptop-a drives o/r#14 and CROOM is that work item's room
        When a message envelope arrives on the Socket Mode connection
        Then the ack is sent only once the event is in the store, laptop-a's queue
             holds it with the payload verbatim, and the log shows subject.appended
             with no classification anywhere

    Requirement: docs/specs/issue-496/requirements.md#requirement-2 (R2.4, R2.5), R1.2, R2.7
    """
    gw.store.claim("loop-github-o-r-14", "laptop-a", "driver")
    client = gw.socket.client
    assert client.connected
    client.deliver("events_api", _message(), envelope_id="env-42")
    assert client.acks == [("env-42", 1)]  # one event stored at ack time
    (delivery,) = gw.fetch("laptop-a").json()["deliveries"]
    assert (
        delivery["event"]["kind"] == "events_api"
        and delivery["event"]["source"] == "socket"
    )
    assert delivery["event"]["deliveryId"] == "env-42"
    assert delivery["event"]["payload"] == _message()
    assert gw.events("subject.appended") and not gw.events("channel.reply_received")


def test_the_heartbeat_is_consumed_by_the_connection_and_never_stored(gw):
    """
    Feature: one Slack app serves every instance through the gateway
      Scenario: the doctor's heartbeat feeds the split check, not a queue
    Requirement: docs/specs/issue-496/design.md §gateway/adapters (slack_socket.py)
    """
    beat = _message(bot_id="B1", text=f"{slack_mod.HEARTBEAT_MARKER} deadbeef")
    nonce = slack_mod.heartbeat_nonce(beat["event"])
    assert nonce == "deadbeef"
    gw.socket.client.deliver("events_api", beat, envelope_id="env-hb")
    assert gw.watch.seen == [nonce]
    assert gw.socket.client.acks == [("env-hb", 0)]
    assert gw.client.get("/api/v1/gateway/subjects").json()["subjects"] == []


def test_a_store_failure_withholds_the_ack_so_slack_redelivers(gw, monkeypatch):
    """
    Feature: one Slack app serves every instance through the gateway
      Scenario: a store failure withholds the ack
    Requirement: docs/specs/issue-496/requirements.md#requirement-2 (R2.4)
    """

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(gw.store, "append", boom)
    gw.socket.client.deliver("events_api", _message(), envelope_id="env-x")
    assert gw.socket.client.acks == []


def test_a_slack_envelope_is_acknowledged_within_three_seconds_with_two_thousand_rows_stored(
    gw,
):
    """
    Feature: one Slack app serves every instance through the gateway
      Scenario: a Slack envelope is acknowledged within three seconds with two thousand rows stored
    Requirement: docs/specs/issue-496/requirements.md#requirement-2 (R2.5); testing plan T7
    """
    gw.store.claim("loop-github-o-r-14", "laptop-a", "driver")
    for n in range(2000):
        gw.append(n, consumers=["laptop-a"], delivery_id=f"bulk-{n}")
    started = time.monotonic()
    gw.socket.client.deliver(
        "events_api", _message(event_id="Ev-late"), envelope_id="env-late"
    )
    took = time.monotonic() - started
    assert gw.socket.client.acks[-1][0] == "env-late"
    assert took < 3.0, took


# -- the HTTP routes (R6.4, R7.2; abuse case 2) -----------------------------------------------------


def _signed(
    body: bytes,
    *,
    ts: int | None = None,
    secret: str = SIGNING,
    content_type="application/json",
) -> dict:
    ts = int(time.time()) if ts is None else ts
    sig = (
        "v0="
        + hmac.new(
            secret.encode(), b"v0:" + str(ts).encode() + b":" + body, hashlib.sha256
        ).hexdigest()
    )
    return {
        "X-Slack-Signature": sig,
        "X-Slack-Request-Timestamp": str(ts),
        "Content-Type": content_type,
    }


def test_the_http_route_answers_the_challenge_and_stores_events_after_verifying(gw):
    """
    Feature: one Slack app serves every instance through the gateway
      Scenario: the HTTP events route verifies the v0 signature and answers url_verification
    Requirement: docs/specs/issue-496/requirements.md#requirement-7 (R7.2), R6.4
    """
    challenge = json.dumps({"type": "url_verification", "challenge": "abc123"}).encode()
    response = gw.client.post(
        "/slack/events", content=challenge, headers=_signed(challenge)
    )
    assert response.status_code == 200 and response.text == "abc123"
    gw.store.claim("loop-github-o-r-14", "laptop-a", "driver")
    body = json.dumps(_message(event_id="Ev-http")).encode()
    assert (
        gw.client.post("/slack/events", content=body, headers=_signed(body)).status_code
        == 200
    )
    (delivery,) = gw.fetch("laptop-a").json()["deliveries"]
    assert (
        delivery["event"]["source"] == "webhook"
        and delivery["event"]["deliveryId"] == "Ev-http"
    )
    bad = gw.client.post(
        "/slack/events", content=body, headers=_signed(body, secret="wrong")
    )
    assert bad.status_code == 401 and bad.json()["status"] == "bad-signature"


def test_a_replayed_slack_delivery_is_refused(gw):
    """
    Feature: one Slack app serves every instance through the gateway
      Scenario: a replayed Slack delivery is refused
        Given a correctly signed events_api body whose timestamp is ten minutes old
        When it is posted to /slack/events
        Then the answer is 401 replay-window, nothing is stored, gateway.dropped says so

    Requirement: docs/specs/issue-496/requirements.md §Security considerations, abuse case 2
    """
    body = json.dumps(_message(event_id="Ev-old")).encode()
    stale = gw.client.post(
        "/slack/events", content=body, headers=_signed(body, ts=int(time.time()) - 600)
    )
    assert stale.status_code == 401 and stale.json()["status"] == "replay-window"
    assert gw.client.get("/api/v1/gateway/subjects").json()["subjects"] == []
    assert gw.events("gateway.dropped")[-1]["reason"] == "replay-window"


def test_a_socket_and_an_http_copy_of_one_event_store_one_row(gw):
    """
    Feature: one Slack app serves every instance through the gateway
      Scenario: a socket and an HTTP route on one app never double-deliver
    Requirement: docs/specs/issue-496/requirements.md#requirement-7 (R7.3)
    """
    gw.store.claim("loop-github-o-r-14", "laptop-a", "driver")
    gw.socket.client.deliver(
        "events_api", _message(event_id="Ev-both"), envelope_id="env-both"
    )
    body = json.dumps(_message(event_id="Ev-both")).encode()
    assert (
        gw.client.post("/slack/events", content=body, headers=_signed(body)).status_code
        == 200
    )
    (row,) = gw.client.get("/api/v1/gateway/subjects").json()["subjects"]
    assert row["events"] == 1


def test_interactions_and_commands_are_form_posts(gw):
    """
    Feature: one Slack app serves every instance through the gateway
      Scenario: a button press and a slash command reach the queue as interactive and slash_commands
    Requirement: docs/specs/issue-496/requirements.md#requirement-5 (R5.9), R6.4
    """
    gw.store.claim("loop-github-o-r-14", "laptop-a", "driver")
    gw.store.bind("slack", "CROOM:1700.1", "github:o/r#14", "github-o-r-14")
    press = {
        "type": "block_actions",
        "trigger_id": "T-1",
        "user": {"id": "U1"},
        "container": {"channel_id": "CROOM", "thread_ts": "1700.1"},
    }
    body = urlencode({"payload": json.dumps(press)}).encode()
    headers = _signed(body, content_type="application/x-www-form-urlencoded")
    assert (
        gw.client.post("/slack/interactions", content=body, headers=headers).status_code
        == 200
    )
    cmd = urlencode(
        {
            "command": "/the-loop",
            "text": "status",
            "channel_id": "CROOM",
            "user_id": "U1",
            "trigger_id": "T-2",
        }
    ).encode()
    headers = _signed(cmd, content_type="application/x-www-form-urlencoded")
    assert (
        gw.client.post("/slack/commands", content=cmd, headers=headers).status_code
        == 200
    )
    kinds = [d["event"]["kind"] for d in gw.fetch("laptop-a").json()["deliveries"]]
    assert kinds == ["interactive", "slash_commands"]


# -- the extracted classifier (design §Trade-offs: one classifier) -----------------------------------


def test_dispatch_envelope_routes_each_shape_to_todays_handler(monkeypatch):
    """
    Feature: one classifier, two transports
      Scenario: dispatch_envelope hands each envelope shape to the handler the listener used
    Requirement: docs/specs/issue-496/requirements.md#requirement-5 (R5.6)
    """
    from the_loop.channels import commands, inbound

    calls = []
    monkeypatch.setattr(
        inbound,
        "handle_socket_event",
        lambda e, c, addressed: calls.append(("event", e["type"], addressed)),
    )
    monkeypatch.setattr(
        inbound, "handle_socket_action", lambda p, c: calls.append(("action",))
    )
    monkeypatch.setattr(
        inbound, "handle_message_action", lambda p, c: calls.append(("message-action",))
    )
    monkeypatch.setattr(
        inbound, "handle_view_submission", lambda p, c: calls.append(("view",))
    )
    monkeypatch.setattr(
        commands, "handle_slash_command", lambda p, c: calls.append(("slash",))
    )
    cfg = {}
    assert (
        slack_mod.dispatch_envelope("slash_commands", {"command": "/the-loop"}, cfg)
        == "handled:slash-command"
    )
    assert (
        slack_mod.dispatch_envelope("interactive", {"type": "block_actions"}, cfg)
        == "handled:block-actions"
    )
    assert (
        slack_mod.dispatch_envelope("interactive", {"type": "message_action"}, cfg)
        == "handled:message-action"
    )
    assert (
        slack_mod.dispatch_envelope("interactive", {"type": "view_submission"}, cfg)
        == "handled:view-submission"
    )
    assert (
        slack_mod.dispatch_envelope("interactive", {"type": "shortcut"}, cfg)
        == "ignored:interactive-kind"
    )
    assert (
        slack_mod.dispatch_envelope(
            "events_api", {"event": {"type": "app_mention"}}, cfg
        )
        == "handled:app-mention"
    )
    assert (
        slack_mod.dispatch_envelope(
            "events_api", {"event": {"type": "message", "text": "hi"}}, cfg
        )
        == "handled:message"
    )
    assert (
        slack_mod.dispatch_envelope(
            "events_api", {"event": {"type": "reaction_added"}}, cfg
        )
        == "ignored:event-type"
    )
    assert slack_mod.dispatch_envelope("other", {}, cfg) == "ignored:envelope-type"
    assert calls == [
        ("slash",),
        ("action",),
        ("message-action",),
        ("view",),
        ("event", "app_mention", True),
        ("event", "message", False),
    ]
