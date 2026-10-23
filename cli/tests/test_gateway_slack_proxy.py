"""Unit tests for the gateway's Slack pass-through (issue-519, T1/T3/T8/T10 — R2, R3,
R4.6, R5.3, R5.4, R6; abuse cases 1, 4, 5).

Run with: pytest (from the cli/ directory). ``-k config`` is task 1, ``-k proxy`` task 2,
``-k route`` task 3, ``-k abuse`` the negative tests, ``-k migration`` the upgrade row.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from the_loop import configschema
from the_loop.gateway import config as gwconfig

BOT_ENV = "THE_LOOP_TEST_GW_BOT_TOKEN"
APP_ENV = "THE_LOOP_TEST_GW_APP_TOKEN"

MINIMAL = {"version": "1", "listen": {"host": "127.0.0.1", "port": 8790}}
SLACK = {
    "socket": {"enabled": True, "appTokenEnv": APP_ENV, "botTokenEnv": BOT_ENV},
}


def _write(tmp_path: Path, body: dict) -> Path:
    path = tmp_path / "gateway-config.yaml"
    path.write_text(yaml.safe_dump(body), encoding="utf-8")
    return path


# -- task 1: the `slack.post` block (R6.1, R6.3, NFR compatibility) ---------------------------


def test_config_migration_a_20_9_0_file_without_slack_post_reads_posting_on(tmp_path):
    """A 20.9.0 file has no `slack.post`; it validates and posting defaults to on
    (R6.1, T10 migration)."""
    conf = gwconfig.load_gateway_config(_write(tmp_path, {**MINIMAL, "slack": SLACK}))
    assert conf.slack is not None
    assert conf.slack.post.enabled is True


def test_config_migration_an_instance_config_from_20_9_0_posts_with_its_local_token(
    tmp_path, monkeypatch
):
    """T10: an instance config unchanged from 20.9.0 — a gateway block and a local bot
    token — posts with its own token as before and never calls the gateway (R4.1)."""
    from the_loop.channels import slack as slack_mod
    from the_loop.channels.slack import SlackChannelConfig

    env = "THE_LOOP_TEST_MIGRATION_BOT_TOKEN"
    monkeypatch.setenv(env, "xoxb-local")
    config = {
        "state": {"root": str(tmp_path / "state")},
        "gateway": {"url": "http://127.0.0.1:8790"},
        "channels": {"slack": {"enabled": True, "channel": "C1", "botTokenEnv": env}},
    }
    seen = []
    client = slack_mod.outbound_client(
        SlackChannelConfig.from_mapping(config),
        config,
        lambda token: seen.append(token),
    )
    assert client is None and seen == ["xoxb-local"]
    assert (
        slack_mod.posting_path(SlackChannelConfig.from_mapping(config), config).kind
        == "local"
    )


def test_config_slack_post_disabled_parses(tmp_path):
    body = {**MINIMAL, "slack": {**SLACK, "post": {"enabled": False}}}
    conf = gwconfig.load_gateway_config(_write(tmp_path, body))
    assert conf.slack is not None and conf.slack.post.enabled is False


def test_config_slack_post_is_in_the_schema_with_a_description_and_default():
    """The onboarding walk asks from the schema's description (R6.4); the default is on."""
    schema = configschema.load_schema("gateway-config")
    post = schema["properties"]["slack"]["properties"]["post"]
    assert post["additionalProperties"] is False
    enabled = post["properties"]["enabled"]
    assert enabled["type"] == "boolean" and enabled["default"] is True
    assert "issue-519" in enabled["description"]
    bot = schema["properties"]["slack"]["properties"]["socket"]["properties"][
        "botTokenEnv"
    ]
    assert "posting" in bot["description"]


def test_config_slack_post_unknown_key_is_refused(tmp_path):
    body = {**MINIMAL, "slack": {**SLACK, "post": {"enabled": True, "channels": []}}}
    with pytest.raises(gwconfig.ConfigError) as info:
        gwconfig.load_gateway_config(_write(tmp_path, body))
    assert "slack.post" in str(info.value)


def test_config_template_carries_slack_post():
    template = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "the-loop"
        / "templates"
        / "gateway-config.yaml"
    )
    if not template.is_file():
        pytest.skip("plugin tree not present (source distribution)")
    conf = gwconfig.load_gateway_config(template)
    assert conf.slack is not None and conf.slack.post.enabled is True
    assert "post:" in template.read_text(encoding="utf-8")


def test_config_slack_post_is_not_a_restart_key(tmp_path):
    """Hot-reloaded (R6.3): flipping it is not among the start-time-only keys."""
    from the_loop.gateway.ingresses import restart_required

    on = gwconfig.load_gateway_config(_write(tmp_path, {**MINIMAL, "slack": SLACK}))
    off = gwconfig.load_gateway_config(
        _write(tmp_path, {**MINIMAL, "slack": {**SLACK, "post": {"enabled": False}}})
    )
    assert restart_required(on, off) == []


# -- task 2: the proxy (R2.1–R2.4, R2.6, R3.1, R3.2; abuse cases 1, 4, 5) --------------------


class _Resp:
    def __init__(self, status, data, headers=None):
        self.status_code = status
        self.data = data
        self.headers = headers or {}


class FakeWebClient:
    """The slice of ``slack_sdk.WebClient`` the proxy uses: ``api_call``."""

    def __init__(self, token):
        self.token = token
        self.calls = []
        self.fail = None

    def api_call(self, method, *, http_verb="POST", json=None, params=None, **_):
        from slack_sdk.errors import SlackApiError, SlackClientError

        self.calls.append((method, json, params))
        if self.fail == "api":
            raise SlackApiError(
                "channel_not_found",
                _Resp(200, {"ok": False, "error": "channel_not_found"}),
            )
        if self.fail == "ratelimit":
            raise SlackApiError(
                "ratelimited",
                _Resp(429, {"ok": False, "error": "ratelimited"}, {"Retry-After": "3"}),
            )
        if self.fail == "transport":
            raise SlackClientError("connection reset")
        channel = (json or params or {}).get("channel")
        return _Resp(200, {"ok": True, "ts": "1700.000001", "channel": channel})


@pytest.fixture()
def proxy_env(monkeypatch, tmp_path):
    from gateway_support import GatewayHarness
    from the_loop.gateway import slack_proxy

    monkeypatch.setenv(BOT_ENV, "xoxb-test")
    monkeypatch.setenv(APP_ENV, "xapp-test")
    gw = GatewayHarness(tmp_path, slack=SLACK)
    web = {}

    def factory(token):
        # the proxy builds a client per call (design §2); the fake is kept so a test
        # can set `fail` once and watch the next call
        client = web.get("client") or FakeWebClient(token)
        client.token = token
        web["client"] = client
        return client

    proxy = slack_proxy.SlackProxy(gw.state, web_client_factory=factory)
    yield gw, proxy, web
    gw.close()


def test_proxy_forwards_every_allowed_method_with_a_json_body(proxy_env):
    from the_loop.gateway import slack_proxy

    gw, proxy, web = proxy_env
    for method in sorted(slack_proxy.SLACK_METHODS):
        result = proxy.call("a", method, {"channel": "C1", "text": "hi"})
        assert result.status == 200 and result.body["ok"] is True, method
        assert web["client"].calls[-1] == (
            method,
            {"channel": "C1", "text": "hi"},
            None,
        )
    assert web["client"].token == "xoxb-test"
    assert len(slack_proxy.SLACK_METHODS) == 14


def test_proxy_returns_slacks_status_and_body_verbatim_when_ok_is_false(proxy_env):
    gw, proxy, web = proxy_env
    proxy.call("a", "auth.test", {})
    web["client"].fail = "api"
    result = proxy.call("a", "chat.update", {"channel": "C1", "ts": "1", "text": "x"})
    assert result.status == 200
    assert result.body == {"ok": False, "error": "channel_not_found"}
    web["client"].fail = "ratelimit"
    result = proxy.call("a", "chat.postMessage", {"channel": "C1", "text": "x"})
    assert result.status == 429 and result.headers["Retry-After"] == "3"
    assert result.body["error"] == "ratelimited"


def test_proxy_transport_failure_is_502_slack_unreachable(proxy_env):
    gw, proxy, web = proxy_env
    proxy.call("a", "auth.test", {})
    web["client"].fail = "transport"
    result = proxy.call("a", "chat.postMessage", {"channel": "C1", "text": "x"})
    assert result.status == 502 and result.body["error"] == "slack-unreachable"
    assert "SlackClientError" in result.body["detail"]


def test_proxy_available_names_its_reason(proxy_env, monkeypatch, tmp_path):
    from gateway_support import GatewayHarness
    from the_loop.gateway import slack_proxy

    gw, proxy, _ = proxy_env
    assert proxy.available() == (True, "")
    monkeypatch.delenv(BOT_ENV)
    assert proxy.available() == (False, "no-token")
    monkeypatch.setenv(BOT_ENV, "xoxb-test")
    off = GatewayHarness(tmp_path / "off", slack={**SLACK, "post": {"enabled": False}})
    try:
        assert slack_proxy.SlackProxy(off.state).available() == (False, "disabled")
    finally:
        off.close()
    bare = GatewayHarness(tmp_path / "bare")
    try:
        assert slack_proxy.SlackProxy(bare.state).available() == (
            False,
            "socket-unconfigured",
        )
    finally:
        bare.close()


def test_proxy_available_follows_a_reloaded_config(proxy_env):
    """R6.3: the flag is read from the live config, so a reload needs no restart."""
    import dataclasses

    from the_loop.gateway.config import SlackPost

    gw, proxy, _ = proxy_env
    assert proxy.available()[0] is True
    gw.state.config = dataclasses.replace(
        gw.state.config,
        slack=dataclasses.replace(gw.state.config.slack, post=SlackPost(enabled=False)),
    )
    assert proxy.available() == (False, "disabled")


def test_proxy_logs_method_channel_and_status_never_text(proxy_env):
    gw, proxy, web = proxy_env
    proxy.call("a", "chat.postMessage", {"channel": "C1", "text": "SECRET WORDS"})
    rows = gw.events("gateway.slack_call")
    assert len(rows) == 1
    row = rows[0]
    assert row["instance"] == "a" and row["method"] == "chat.postMessage"
    assert row["channel"] == "C1" and row["status"] == 200 and row["ok"] is True
    line = gw.events_path.read_text()
    assert "SECRET WORDS" not in line and "xoxb-test" not in line


def test_proxy_download_fetches_with_slack_hosts_and_the_cap(proxy_env):
    from the_loop.channels import attachments
    from the_loop.gateway import slack_proxy

    gw, _, _ = proxy_env
    seen = {}

    def fetch(url, *, credential="", allowed_hosts=(), max_bytes=0, **_):
        seen.update(url=url, credential=credential, hosts=allowed_hosts, cap=max_bytes)
        return "audio/mp4", b"\x00\x01"

    proxy = slack_proxy.SlackProxy(gw.state, fetch=fetch)
    result = proxy.download("a", "https://files.slack.com/files-pri/T1-F1/clip.m4a")
    assert result.status == 200 and result.body == b"\x00\x01"
    assert result.media_type == "audio/mp4"
    assert seen["credential"] == "xoxb-test"
    assert seen["hosts"] == attachments.SLACK_HOSTS
    assert seen["cap"] == attachments.MAX_BYTES
    row = gw.events("gateway.slack_download")[0]
    assert row["instance"] == "a" and row["status"] == 200
    assert "xoxb" not in gw.events_path.read_text()


def test_abuse_1_a_method_outside_the_allow_list_is_422_and_nothing_is_sent(proxy_env):
    gw, proxy, web = proxy_env
    result = proxy.call("a", "conversations.invite", {"channel": "C1", "users": "U1"})
    assert result.status == 422 and result.body["error"] == "method-not-allowed"
    assert "client" not in web  # the web client was never even built
    result = proxy.call("a", "admin.users.remove", {})
    assert result.status == 422 and "client" not in web
    refused = gw.events("gateway.refused")
    assert refused and refused[-1]["method"] == "admin.users.remove"


def test_abuse_7_a_token_in_params_is_refused_before_the_sdk_sees_it(proxy_env):
    """Security review (issue-519): slack_sdk pops `token` from the JSON body and uses
    it instead of the client's, so a peer could route a credential of its own through
    the gateway under the gateway's name. Refused at the proxy, nothing sent."""
    gw, proxy, web = proxy_env
    result = proxy.call(
        "a", "chat.postMessage", {"channel": "C1", "text": "x", "token": "xoxb-other"}
    )
    assert result.status == 422
    assert (
        result.body["error"] == "param-not-allowed" and result.body["param"] == "token"
    )
    assert "client" not in web
    refused = gw.events("gateway.refused")
    assert refused[-1]["reason"] == "param-not-allowed"
    assert "xoxb-other" not in gw.events_path.read_text()


def test_abuse_5_posting_disabled_is_503_and_sends_nothing(monkeypatch, tmp_path):
    from gateway_support import GatewayHarness
    from the_loop.gateway import slack_proxy

    monkeypatch.setenv(BOT_ENV, "xoxb-test")
    gw = GatewayHarness(tmp_path, slack={**SLACK, "post": {"enabled": False}})
    built = []
    try:
        proxy = slack_proxy.SlackProxy(
            gw.state, web_client_factory=lambda t: built.append(t) or FakeWebClient(t)
        )
        result = proxy.call("a", "chat.postMessage", {"channel": "C1", "text": "x"})
        assert result.status == 503
        assert result.body == {"error": "posting-unavailable", "reason": "disabled"}
        result = proxy.download("a", "https://files.slack.com/f")
        assert result.status == 503 and result.body["reason"] == "disabled"
        assert built == []
    finally:
        gw.close()


def test_abuse_5b_no_token_on_the_gateway_is_503_no_token(proxy_env, monkeypatch):
    gw, proxy, web = proxy_env
    monkeypatch.delenv(BOT_ENV)
    result = proxy.call("a", "chat.postMessage", {"channel": "C1", "text": "x"})
    assert result.status == 503 and result.body["reason"] == "no-token"
    assert "client" not in web


def test_abuse_4_download_refuses_off_host_and_over_cap_before_any_fetch(proxy_env):
    from the_loop.channels.attachments import FetchError
    from the_loop.gateway import slack_proxy

    gw, _, _ = proxy_env
    calls = []

    def fetch(url, **kw):
        calls.append(url)
        raise FetchError("over-cap", "26 MiB")

    proxy = slack_proxy.SlackProxy(gw.state, fetch=fetch)
    result = proxy.download("a", "https://evil.example.com/files-pri/x")
    assert result.status == 422 and result.body["error"] == "off-host"
    result = proxy.download("a", "http://files.slack.com/not-https")
    assert result.status == 422 and result.body["error"] == "off-host"
    assert calls == []  # refused before the fetch
    result = proxy.download("a", "https://files.slack.com/files-pri/T1-F1/big.bin")
    assert result.status == 413 and result.body["error"] == "over-cap"
    assert calls == ["https://files.slack.com/files-pri/T1-F1/big.bin"]

    def failing(url, **kw):
        raise FetchError("transfer-failed", "HTTP 500")

    proxy = slack_proxy.SlackProxy(gw.state, fetch=failing)
    result = proxy.download("a", "https://files.slack.com/files-pri/T1-F1/clip.m4a")
    assert result.status == 502 and result.body["error"] == "transfer-failed"


# -- task 3: the routes, health, the contract and `gateway status` (R2.1, R2.5, R4.6,
#    R5.3, R5.4, R6.2) ------------------------------------------------------------------------


@pytest.fixture()
def route_env(monkeypatch, tmp_path):
    from gateway_support import GatewayHarness
    from the_loop.gateway import slack_proxy

    monkeypatch.setenv(BOT_ENV, "xoxb-test")
    monkeypatch.setenv(APP_ENV, "xapp-test")
    gw = GatewayHarness(tmp_path, slack=SLACK, instances=["a", "b"])
    web = {}

    def factory(token):
        client = web.get("client") or FakeWebClient(token)
        web["client"] = client
        return client

    gw.state.slack_proxy = slack_proxy.SlackProxy(gw.state, web_client_factory=factory)
    yield gw, web
    gw.close()


def _call(gw, instance="a", peer="p", method="chat.postMessage", params=None):
    return gw.client.post(
        "/api/v1/gateway/slack/call",
        json={
            "instance": instance,
            "peer": peer,
            "method": method,
            "params": params if params is not None else {"channel": "C1", "text": "hi"},
        },
    )


def test_route_slack_call_forwards_and_returns_slacks_answer(route_env):
    gw, web = route_env
    response = _call(gw)
    assert response.status_code == 200
    assert response.json() == {"ok": True, "ts": "1700.000001", "channel": "C1"}
    assert web["client"].calls == [
        ("chat.postMessage", {"channel": "C1", "text": "hi"}, None)
    ]
    web["client"].fail = "ratelimit"
    response = _call(gw)
    assert response.status_code == 429 and response.headers["Retry-After"] == "3"
    assert response.json()["error"] == "ratelimited"


def test_route_slack_call_unknown_method_is_422(route_env):
    gw, web = route_env
    response = _call(gw, method="conversations.invite")
    assert response.status_code == 422
    assert response.json()["error"] == "method-not-allowed"
    assert "client" not in web


def test_route_slack_call_applies_the_instance_allow_list_and_the_peer_lease(route_env):
    """R5.3: the two guards every consumer route has, nothing more."""
    gw, web = route_env
    response = _call(gw, instance="stranger")
    assert response.status_code == 409
    assert response.json()["error"] == "unknown-instance"
    gw.fetch("a", peer="holder")  # a live lease under the name
    response = _call(gw, instance="a", peer="other")
    assert response.status_code == 409
    assert response.json()["error"] == "duplicate-instance"
    assert "client" not in web
    response = _call(gw, instance="a", peer="holder")
    assert response.status_code == 200


def test_route_slack_call_bounds_are_422_at_the_door(route_env):
    """R5.4: an oversized method, params or url is refused before anything is read."""
    gw, web = route_env
    response = _call(gw, method="x" * 65)
    assert response.status_code == 422
    response = _call(gw, params={"channel": "C1", "text": "y" * (256 * 1024 + 1)})
    assert response.status_code == 422
    response = gw.client.post(
        "/api/v1/gateway/slack/download",
        json={
            "instance": "a",
            "peer": "p",
            "url": "https://files.slack.com/" + "u" * 2050,
        },
    )
    assert response.status_code == 422
    assert "client" not in web


def test_route_slack_download_returns_the_bytes_with_their_type(route_env):
    from the_loop.gateway import slack_proxy

    gw, _ = route_env
    gw.state.slack_proxy = slack_proxy.SlackProxy(
        gw.state, fetch=lambda url, **kw: ("audio/mp4", b"\x00\x01\x02")
    )
    response = gw.client.post(
        "/api/v1/gateway/slack/download",
        json={
            "instance": "a",
            "peer": "p",
            "url": "https://files.slack.com/f/clip.m4a",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mp4")
    assert response.content == b"\x00\x01\x02"
    response = gw.client.post(
        "/api/v1/gateway/slack/download",
        json={"instance": "a", "peer": "p", "url": "https://evil.example/f"},
    )
    assert response.status_code == 422 and response.json()["error"] == "off-host"


def test_route_slack_call_is_503_when_posting_is_unavailable(route_env, monkeypatch):
    gw, web = route_env
    monkeypatch.delenv(BOT_ENV)
    response = _call(gw)
    assert response.status_code == 503
    assert response.json() == {"error": "posting-unavailable", "reason": "no-token"}
    assert "client" not in web


def test_route_health_carries_slack_posting(route_env, monkeypatch):
    """R4.6: the instance reads whether the gateway posts from health."""
    gw, _ = route_env
    health = gw.client.get("/api/v1/gateway/health").json()
    assert health["slack"]["posting"] == "on"
    monkeypatch.delenv(BOT_ENV)
    health = gw.client.get("/api/v1/gateway/health").json()
    assert health["slack"]["posting"] == "no-token"


def test_route_gateway_status_reports_posting(route_env, monkeypatch):
    """R6.2: `gateway status` prints posting and carries it in --format json."""
    from the_loop.commands import gateway_cmd

    gw, _ = route_env

    class _HeldLock:
        def __init__(self, *a, **k):
            pass

        def is_held(self):
            return True

        def holder(self):
            return 4242

    monkeypatch.setattr(gateway_cmd, "RunLock", _HeldLock)
    health = gw.client.get("/api/v1/gateway/health").json()
    monkeypatch.setattr(
        gateway_cmd,
        "_get",
        lambda config, what: health if what == "health" else {"instances": []},
    )
    report = gateway_cmd.status_report(gw.config)
    assert report["slackPosting"] == "on"
    lines = gateway_cmd.status_lines(report)
    assert any(line.strip() == "slack posting: on" for line in lines)
