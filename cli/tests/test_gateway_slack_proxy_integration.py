"""Integration scenarios for outbound Slack through the gateway (issue-519, T2/T8 —
R1, R2, R3, R4.1, R4.2, R4.4, R4.7): the instance's real Slack channel on the real bus,
its gateway-backed client talking to a real gateway app in-process, a fake Slack Web API
on the gateway, and the gateway's Slack HTTP ingress for the reply. No network, no
credential on the instance.

Feature: an instance behind a gateway posts to Slack with the gateway's token
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import pytest

from gateway_support import GatewayHarness
from the_loop.channels import bus, outbox
from the_loop.channels import slack as slack_mod
from the_loop.channels.base import Event, load_channels
from the_loop.channels.slack_gateway import GatewaySlackClient
from the_loop.channels.state import ChannelState
from the_loop.gateway import client as gateway_client_mod
from the_loop.gateway import slack_proxy
from the_loop.gateway.adapters.ingest import Ingest
from the_loop.gateway.adapters.slack_http import build_slack_http_router
from the_loop.gateway.config import SlackPost

GW_BOT_ENV = "THE_LOOP_TEST_GW_BOT_TOKEN"
GW_APP_ENV = "THE_LOOP_TEST_GW_APP_TOKEN"
INSTANCE_BOT_ENV = "THE_LOOP_TEST_INSTANCE_BOT_TOKEN"
SIGNING = "slack-signing-secret"
REF = "github:o/r#14"
SUBJECT = "loop-github-o-r-14"
CENTRAL = "C0CENTRAL"
ROOM = "C0ROOM519"
BOT = "UBOT"
HUMAN = "UHUMAN"
VTT = "WEBVTT\n\n00:00.000 --> 00:02.000\nplease make the button blue\n"


# -- the gateway side: a real app, a fake Slack --------------------------------------------------


class _Resp:
    def __init__(self, status, data, headers=None):
        self.status_code, self.data, self.headers = status, data, headers or {}


class FakeSlackWeb:
    """The Slack Web API as the gateway sees it: one `api_call`, answers per method."""

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self.ts = 0

    def api_call(self, method, *, http_verb="POST", json=None, params=None, **_):
        payload = dict(json or params or {})
        self.calls.append({"method": method, **payload})
        if method == "chat.postMessage":
            self.ts += 1
            return _Resp(
                200,
                {
                    "ok": True,
                    "channel": payload.get("channel"),
                    "ts": f"1700.{self.ts:06d}",
                },
            )
        if method == "auth.test":
            return _Resp(
                200, {"ok": True, "user_id": BOT, "url": "https://x.slack.com/"}
            )
        if method == "files.info":
            return _Resp(200, {"ok": True, "file": _audio()})
        if method == "chat.getPermalink":
            return _Resp(
                200, {"ok": True, "permalink": "https://x.slack.com/archives/p1"}
            )
        if method == "conversations.replies":
            return _Resp(200, {"ok": True, "messages": []})
        return _Resp(200, {"ok": True})

    def posted(self) -> List[Dict[str, Any]]:
        return [c for c in self.calls if c["method"] == "chat.postMessage"]


def _audio():
    return {
        "id": "F0AUD",
        "name": "audio_message.m4a",
        "mimetype": "audio/mp4",
        "subtype": "slack_audio",
        "size": 9,
        "permalink": "https://x.slack.com/files/UHUMAN/F0AUD/audio_message.m4a",
        "url_private_download": "https://files.slack.com/files-pri/T0-F0AUD/download/audio_message.m4a",
        "vtt": "https://files.slack.com/files-pri/T0-F0AUD/audio_message.vtt",
        "transcription": {
            "status": "complete",
            "locale": "en-US",
            "preview": {"content": "please make the button blue", "has_more": False},
        },
    }


class Gateway:
    def __init__(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv(GW_BOT_ENV, "xoxb-gateway")
        monkeypatch.setenv(GW_APP_ENV, "xapp-gateway")
        monkeypatch.setenv("SLACK_SIGNING_SECRET", SIGNING)
        self.harness = GatewayHarness(
            tmp_path / "gw",
            slack={
                "socket": {"appTokenEnv": GW_APP_ENV, "botTokenEnv": GW_BOT_ENV},
                "http": {"enabled": True},
            },
        )
        self.harness.app.include_router(
            build_slack_http_router(Ingest(self.harness.state), self.harness.config)
        )
        self.web = FakeSlackWeb()
        self.fetched: List[Tuple[str, str]] = []

        def fetch(url, *, credential="", allowed_hosts=(), max_bytes=0, **_):
            self.fetched.append((url, credential))
            if url.endswith(".vtt"):
                return "text/vtt", VTT.encode()
            return "audio/mp4", b"m4a-bytes"

        self.harness.state.slack_proxy = slack_proxy.SlackProxy(
            self.harness.state, web_client_factory=lambda token: self.web, fetch=fetch
        )

    def transport(self, method, path, body, timeout):
        response = self.harness.client.request(method, path, json=body)
        return response.status_code, (response.json() if response.content else None)

    def download(self, client, url, timeout):
        response = self.harness.client.post(
            "/api/v1/gateway/slack/download",
            json={"instance": client.instance, "peer": client.peer, "url": url},
        )
        return (
            response.status_code,
            response.headers.get("content-type", ""),
            response.content,
        )

    def disable_posting(self) -> None:
        state = self.harness.state
        assert state.config.slack is not None
        state.config = dataclasses.replace(
            state.config,
            slack=dataclasses.replace(state.config.slack, post=SlackPost(False)),
        )

    def slack_reply(self, user: str, ts: str, thread_ts: str, channel: str = CENTRAL):
        body = json.dumps(
            {
                "event_id": f"Ev-{ts}",
                "team_id": "T1",
                "event": {
                    "type": "app_mention",
                    "channel": channel,
                    "ts": ts,
                    "thread_ts": thread_ts,
                    "user": user,
                    "text": f"<@{BOT}> looks good",
                },
            }
        ).encode()
        stamp = str(int(time.time()))
        sig = (
            "v0="
            + hmac.new(
                SIGNING.encode(), b"v0:" + stamp.encode() + b":" + body, hashlib.sha256
            ).hexdigest()
        )
        answer = self.harness.client.post(
            "/slack/events",
            content=body,
            headers={
                "X-Slack-Signature": sig,
                "X-Slack-Request-Timestamp": stamp,
                "Content-Type": "application/json",
            },
        )
        assert answer.status_code == 200

    def close(self) -> None:
        self.harness.close()


@pytest.fixture()
def gw(tmp_path, monkeypatch) -> Iterator[Gateway]:
    gateway = Gateway(tmp_path, monkeypatch)
    # the instance's gateway-backed client reaches the in-process app (what
    # urllib_transport does over the network), for calls and for downloads
    monkeypatch.setattr(
        gateway_client_mod, "urllib_transport", lambda base_url: gateway.transport
    )
    monkeypatch.setattr(
        GatewaySlackClient,
        "_urllib_download",
        lambda self, url, timeout: gateway.download(self, url, timeout),
    )
    yield gateway
    gateway.close()


# -- the instance side: a real channel on the real bus, no token ---------------------------------


def instance_config(tmp_path: Path, *, gateway: bool = True) -> Dict[str, Any]:
    config: Dict[str, Any] = {
        "state": {"root": str(tmp_path / "inst")},
        "instance": {"name": "laptop-a"},
        "service": {"enabled": False},
        "routing": {"authorizedUsers": [{"github": "octocat", "slack": HUMAN}]},
        "channels": {
            "ledger": "github",
            "slack": {
                "enabled": True,
                "channel": CENTRAL,
                "botTokenEnv": INSTANCE_BOT_ENV,
                "publish": ["work-item.reply", "context.added"],
                "read": {"mode": "gateway" if gateway else "poll"},
            },
        },
    }
    if gateway:
        config["gateway"] = {
            "url": "http://gateway.test:8790",
            "actors": {"slack": [HUMAN]},
        }
    return config


@pytest.fixture(autouse=True)
def _no_instance_token(monkeypatch):
    monkeypatch.delenv(INSTANCE_BOT_ENV, raising=False)


@pytest.fixture()
def publisher(gw):
    """What api/ingress.py wires on a hosted instance: a bound thread is published to
    the gateway. Here it calls the harness's bindings route directly."""

    def publish(provider, key, work_item):
        gw.harness.bind(work_item, provider, key, instance="laptop-a", peer="")

    ChannelState.publisher = publish
    yield publish
    ChannelState.publisher = None


def _event(text="Should I use approach A or B?"):
    return Event(
        event_type="session.awaiting_input",
        work_item=REF,
        text=text,
        url="https://github.com/o/r/issues/14#issuecomment-1",
        detail={"actor": "agent"},
    )


def _thread(config) -> Any:
    channel: Any
    (channel,) = load_channels(config)
    return ChannelState.load(channel.state_path, channel.stores).thread_for(REF)


def test_an_instance_with_no_bot_token_opens_a_work_items_thread_through_the_gateway(
    gw, tmp_path, publisher
):
    """
    Feature: an instance behind a gateway posts to Slack with the gateway's token
      Scenario: an instance with no bot token opens a work item's thread through the gateway and binds it
        Given an instance with a gateway block, Slack enabled, and no bot token in its environment
        And a gateway whose Socket Mode ingress holds the app's bot token and whose posting is on
        When the bus publishes the work item's first event
        Then the gateway calls chat.postMessage on Slack with its own token
        And the instance binds the thread Slack returned and publishes the binding to the gateway
        And the event is delivered, not queued

    Requirement: docs/specs/issue-519/requirements.md#requirement-2 (R2.1, R2.2),
                 #requirement-4 (R4.2, R4.7)
    """
    config = instance_config(tmp_path)
    result = bus.publish(_event(), config, record=False)
    assert result.delivered, [p.error for p in result.posts]
    root, reply = (
        gw.web.posted()
    )  # the thread opener, then the event as its first reply
    assert root["channel"] == CENTRAL and root.get("thread_ts") is None
    assert reply["channel"] == CENTRAL and reply["thread_ts"] == "1700.000001"
    assert "approach A or B" in json.dumps(reply)
    assert _thread(config) == (CENTRAL, "1700.000001")
    assert gw.harness.store.resolve("slack", f"{CENTRAL}:1700.000001") == REF
    rows = gw.harness.events("gateway.slack_call")
    assert rows and rows[-1]["method"] == "chat.postMessage" and rows[-1]["ok"] is True
    assert "approach A or B" not in gw.harness.events_path.read_text()
    assert outbox.entries(config) == []


def test_a_reply_in_a_thread_opened_through_the_gateway_reaches_the_work_item(
    gw, tmp_path, publisher
):
    """
    Feature: an instance behind a gateway posts to Slack with the gateway's token
      Scenario: a reply in a thread opened through the gateway reaches the work item
        Given the thread of the previous scenario, bound and published, and the instance's claim on the subject
        When an authorized member replies in that thread with a mention
        Then the gateway routes the event onto the work item's subject by the binding
        And the instance's queue carries it

    Requirement: docs/specs/issue-519/requirements.md#requirement-4 (R4.7)
    """
    config = instance_config(tmp_path)
    assert bus.publish(_event(), config, record=False).delivered
    gw.harness.claim("laptop-a", SUBJECT, peer="")
    gw.slack_reply(HUMAN, "1700.5", thread_ts="1700.000001")
    routed = [
        (r.get("subject"), r.get("by")) for r in gw.harness.events("subject.routed")
    ]
    assert (SUBJECT, "claim") in routed or (SUBJECT, "binding") in routed
    fetched = gw.harness.fetch("laptop-a", peer="").json()["deliveries"]
    slack_deliveries = [d for d in fetched if d["event"]["provider"] == "slack"]
    assert slack_deliveries and slack_deliveries[-1]["event"]["workItem"] == REF
    assert (
        slack_deliveries[-1]["event"]["payload"]["event"]["thread_ts"] == "1700.000001"
    )


def test_a_voice_notes_transcript_reaches_the_session_through_the_gateways_download_route(
    gw, tmp_path, publisher
):
    """
    Feature: an instance behind a gateway posts to Slack with the gateway's token
      Scenario: a voice note's transcript reaches the session through the gateway's download route
        Given the instance has no token and the work item declared a Slack room
        When an authorized member sends a voice clip Slack has transcribed, mentioning the bot
        Then the instance fetches the clip and its captions through the gateway's download route
        And the delivered text quotes Slack's transcript under the saved clip, as with a local token

    Requirement: docs/specs/issue-519/requirements.md#requirement-3 (R3.1, R3.3)
    """
    from the_loop.channels import inbound
    from the_loop.workchannels import CollaborationChannelStore

    config = instance_config(tmp_path)
    CollaborationChannelStore(Path(config["state"]["root"]) / "portable").add(
        REF, f"slack@{ROOM}", actor="octocat", source="cli", listen="mentions"
    )
    delivered: List[Dict[str, Any]] = []
    recorded: List[Any] = []

    def deliver(ref, text, actor="", comment=True, config=None, **extra):
        delivered.append({"ref": ref, "text": text})
        return {"delivered": True}

    def post_comment(item, body, **kwargs):
        recorded.append(body)
        return True, "", "https://github.com/o/r/issues/14#issuecomment-2"

    event = {
        "ts": "1900.5",
        "channel": ROOM,
        "user": HUMAN,
        "text": f"<@{BOT}>",
        "files": [_audio()],
    }
    inbound.handle_socket_event(
        event, config, post_comment=post_comment, deliver=deliver, addressed=True
    )
    assert delivered, recorded
    text = delivered[0]["text"]
    assert "audio_message.m4a (audio/mp4" in text and "saved at" in text
    assert 'Slack\'s transcript: "please make the button blue"' in text
    urls = [url for url, _ in gw.fetched]
    assert any(url.endswith(".vtt") for url in urls) and any(
        "F0AUD" in url for url in urls
    )
    assert all(credential == "xoxb-gateway" for _, credential in gw.fetched)
    assert gw.harness.events("gateway.slack_download")
    assert "xoxb-gateway" not in gw.harness.events_path.read_text()


def test_an_instance_with_a_local_token_never_calls_the_gateway(
    gw, tmp_path, monkeypatch
):
    """
    Feature: an instance behind a gateway posts to Slack with the gateway's token
      Scenario: an instance with a local token never calls the gateway
        Given an instance with a gateway block AND its own bot token set
        When the bus publishes an event
        Then the post goes to Slack with the local token
        And the gateway's Slack call route is never asked

    Requirement: docs/specs/issue-519/requirements.md#requirement-4 (R4.1)
    """
    from test_channels import FakeSlackClient

    monkeypatch.setenv(INSTANCE_BOT_ENV, "xoxb-local")
    local = FakeSlackClient()
    monkeypatch.setattr(slack_mod, "build_client", lambda token: local)
    config = instance_config(tmp_path)
    result = bus.publish(_event(), config, record=False)
    assert result.delivered
    assert len(local.posted) == 2  # the opener and the reply, both on the local client
    assert gw.web.calls == [] and gw.harness.events("gateway.slack_call") == []


def test_an_instance_with_neither_path_warns_at_start_and_the_post_fails(
    tmp_path, monkeypatch, caplog
):
    """
    Feature: an instance behind a gateway posts to Slack with the gateway's token
      Scenario: an instance with neither path warns at start and the post fails
        Given Slack enabled, no bot token and no gateway block
        When `the-loop start` composes its services and the bus later publishes an event
        Then start logs one warning naming the variable and still succeeds
        And the post fails with today's error plus the gateway hint, and the event waits in the outbox

    Requirement: docs/specs/issue-519/requirements.md#requirement-1 (R1.1, R1.6),
                 #requirement-4 (R4.3)
    """
    from the_loop.core import lifecycle

    config = instance_config(tmp_path, gateway=False)
    caplog.set_level(logging.WARNING)
    report = lifecycle.start_all(config)
    assert report["ok"] is True
    warnings = [r.getMessage() for r in caplog.records if "outbound" in r.getMessage()]
    assert len(warnings) == 1 and INSTANCE_BOT_ENV in warnings[0]
    result = bus.publish(_event(), config, record=False)
    assert not result.delivered
    (post,) = result.posts
    assert "no bot token" in post.error and "slack.post.enabled" in post.error
    (entry,) = outbox.entries(config)
    assert entry["event"]["workItem"] == REF


def test_a_gateway_that_stops_posting_fails_the_post_and_never_falls_back(
    gw, tmp_path, monkeypatch, publisher
):
    """
    Feature: an instance behind a gateway posts to Slack with the gateway's token
      Scenario: a gateway that stops posting fails the post and never falls back to a local token
        Given an instance with no token behind a gateway whose slack.post.enabled was switched off
        When the bus publishes an event
        Then the gateway answers 503 posting-unavailable and sends nothing to Slack
        And the post fails naming the gateway's reason, the event waits in the outbox,
            and no local token is tried

    Requirement: docs/specs/issue-519/requirements.md#requirement-4 (R4.4),
                 #requirement-6 (R6.1); abuse case 5
    """
    gw.disable_posting()
    monkeypatch.setenv(
        INSTANCE_BOT_ENV, ""
    )  # set-but-empty is unset: nothing to fall back to
    config = instance_config(tmp_path)
    result = bus.publish(_event(), config, record=False)
    assert not result.delivered
    (post,) = result.posts
    assert "posting-unavailable" in post.error and "disabled" in post.error
    assert gw.web.calls == []
    (entry,) = outbox.entries(config)
    assert entry["event"]["workItem"] == REF
    refused = gw.harness.events("gateway.refused")
    assert refused and refused[-1]["reason"] == "posting-unavailable"
