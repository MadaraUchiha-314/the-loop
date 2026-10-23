"""Unit tests for the instance's gateway-backed Slack client (issue-519, T1 — R3.3, R4.2,
R4.4): ``channels/slack_gateway.py`` maps the gateway's answers to what the SDK client
would have given, and never reads a token of its own.

Run with: pytest (from the cli/ directory).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from the_loop.channels import attachments
from the_loop.channels.base import ChannelError

BOT_ENV = "THE_LOOP_TEST_INSTANCE_BOT_TOKEN"


class FakeTransport:
    """``(method, path, body, timeout) -> (status, json)``, recorded, scripted."""

    def __init__(self):
        self.calls = []
        self.answer = (200, {"ok": True, "ts": "1700.000001", "channel": "C1"})
        self.raise_ = None

    def __call__(self, method, path, body, timeout):
        self.calls.append((method, path, body, timeout))
        if self.raise_ is not None:
            raise self.raise_
        return self.answer


def _client(transport=None, **kw):
    from the_loop.channels.slack_gateway import GatewaySlackClient

    return GatewaySlackClient(
        "http://127.0.0.1:8790", "laptop-a", "peer-1", transport=transport, **kw
    )


def test_every_sdk_method_name_is_one_call_to_the_gateway():
    from the_loop.channels.slack_gateway import GatewaySlackClient
    from the_loop.gateway.slack_proxy import SLACK_METHODS

    transport = FakeTransport()
    client = _client(transport)
    for method in sorted(SLACK_METHODS):
        attr = method.replace(".", "_")
        assert hasattr(GatewaySlackClient, attr), attr
        response = getattr(client, attr)(channel="C1", text="hi")
        assert response.get("ok") is True
        verb, path, body, _ = transport.calls[-1]
        assert (verb, path) == ("POST", "/api/v1/gateway/slack/call")
        assert body == {
            "instance": "laptop-a",
            "peer": "peer-1",
            "method": method,
            "params": {"channel": "C1", "text": "hi"},
        }


def test_an_ok_true_answer_is_a_plain_dict_the_callers_already_read():
    client = _client(FakeTransport())
    response = client.chat_postMessage(channel="C1", text="hi")
    assert response["ts"] == "1700.000001" and response.get("channel") == "C1"


def test_slacks_ok_false_is_the_sdks_own_exception():
    """What ``_edit_or_post`` and the best-effort reactions already catch (R4.2)."""
    from slack_sdk.errors import SlackApiError

    transport = FakeTransport()
    transport.answer = (200, {"ok": False, "error": "message_not_found"})
    client = _client(transport)
    with pytest.raises(SlackApiError) as info:
        client.chat_update(channel="C1", ts="1", text="x")
    assert "message_not_found" in str(info.value)
    assert info.value.response["error"] == "message_not_found"
    transport.answer = (429, {"ok": False, "error": "ratelimited"})
    with pytest.raises(SlackApiError):
        client.chat_postMessage(channel="C1", text="x")


@pytest.mark.parametrize(
    "status, body, words",
    [
        (503, {"error": "posting-unavailable", "reason": "disabled"}, "disabled"),
        (503, {"error": "posting-unavailable", "reason": "no-token"}, "no-token"),
        (
            409,
            {"error": "duplicate-instance", "holder": "ab12cd34"},
            "duplicate-instance",
        ),
        (422, {"error": "method-not-allowed", "method": "x.y"}, "method-not-allowed"),
        (
            502,
            {"error": "slack-unreachable", "detail": "OSError: x"},
            "slack-unreachable",
        ),
    ],
)
def test_a_gateway_refusal_is_a_channel_error_naming_the_gateways_answer(
    status, body, words
):
    from the_loop.channels.slack_gateway import GatewayPostingError

    transport = FakeTransport()
    transport.answer = (status, body)
    client = _client(transport)
    with pytest.raises(GatewayPostingError) as info:
        client.chat_postMessage(channel="C1", text="x")
    assert isinstance(info.value, ChannelError)
    assert words in str(info.value) and "gateway" in str(info.value)


def test_an_unreachable_gateway_is_a_channel_error_and_never_a_local_token(monkeypatch):
    from the_loop.channels.slack_gateway import GatewayPostingError

    monkeypatch.setenv(BOT_ENV, "xoxb-should-never-be-read")
    transport = FakeTransport()
    transport.raise_ = OSError("connection refused")
    client = _client(transport)
    with pytest.raises(GatewayPostingError) as info:
        client.chat_postMessage(channel="C1", text="x")
    assert "unreachable" in str(info.value)
    assert "xoxb" not in str(info.value)
    transport.raise_ = None
    transport.answer = (200, "not json")
    with pytest.raises(GatewayPostingError):
        client.auth_test()


def test_fetch_has_fetch_urls_shape_and_maps_the_download_route():
    transport = FakeTransport()
    client = _client(transport)
    # the transport is JSON-only; the download answer is bytes, so the client takes a
    # second, byte-returning transport for it
    client._download = lambda url, timeout: (200, "audio/mp4", b"\x00\x01")  # noqa: SLF001
    media, data = client.fetch(
        "https://files.slack.com/f/clip.m4a",
        credential="ignored",
        allowed_hosts=attachments.SLACK_HOSTS,
        max_bytes=attachments.MAX_BYTES,
    )
    assert (media, data) == ("audio/mp4", b"\x00\x01")


def test_fetch_turns_a_refusal_into_a_fetch_error_with_the_gateways_reason():
    client = _client(FakeTransport())
    client._download = lambda url, timeout: (  # noqa: SLF001
        413,
        "application/json",
        json.dumps({"error": "over-cap", "detail": "26 MiB"}).encode(),
    )
    with pytest.raises(attachments.FetchError) as info:
        client.fetch("https://files.slack.com/f/big.bin")
    assert info.value.reason == "over-cap"
    client._download = lambda url, timeout: (  # noqa: SLF001
        503,
        "application/json",
        json.dumps({"error": "posting-unavailable", "reason": "disabled"}).encode(),
    )
    with pytest.raises(attachments.FetchError) as info:
        client.fetch("https://files.slack.com/f/big.bin")
    assert info.value.reason == "no-token"  # the attachment line's existing word


def test_from_cli_config_reads_the_url_the_name_and_the_persisted_peer(tmp_path):
    from the_loop.channels.slack_gateway import GatewaySlackClient
    from the_loop.gateway.client import PEER_FILE
    from the_loop.state import layout_from_config

    config = {
        "state": {"root": str(tmp_path / "state")},
        "instance": {"name": "laptop-b"},
        "gateway": {"url": "http://gw.local:8790/"},
    }
    local_dir = Path(layout_from_config(config).local_dir)
    client = GatewaySlackClient.from_cli_config(config)
    assert client.url == "http://gw.local:8790" and client.instance == "laptop-b"
    assert client.peer == ""  # the daemon never ran here: no file, an empty peer
    local_dir.mkdir(parents=True, exist_ok=True)
    (local_dir / PEER_FILE).write_text(json.dumps({"peer": "deadbeef"}))
    assert GatewaySlackClient.from_cli_config(config).peer == "deadbeef"


def test_from_cli_config_refuses_a_config_without_a_gateway_block():
    from the_loop.channels.slack_gateway import GatewaySlackClient

    with pytest.raises(ValueError):
        GatewaySlackClient.from_cli_config({"instance": {"name": "x"}})
