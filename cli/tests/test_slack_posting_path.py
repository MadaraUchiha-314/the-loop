"""Unit tests for the instance's posting path (issue-519, T1 — R1.3, R3.3, R4.1–R4.4):
``posting_path`` and ``outbound_client`` in ``channels/slack.py``, and the call sites
that take their Slack client from them — the channel, the directory, the doctor and the
attachment fetcher. Task 6 adds the start / status / doctor wording cases below.

Run with: pytest (from the cli/ directory).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from the_loop.channels import slack as slack_mod
from the_loop.channels.base import ChannelError
from the_loop.channels.slack import SlackChannelConfig

BOT_ENV = "THE_LOOP_TEST_PP_BOT_TOKEN"
GATEWAY_URL = "http://127.0.0.1:8799"


@pytest.fixture(autouse=True)
def _no_token(monkeypatch):
    monkeypatch.delenv(BOT_ENV, raising=False)


def cli_config(tmp_path: Path, *, gateway: bool, slack_enabled: bool = True) -> dict:
    config = {
        "state": {"root": str(tmp_path / "state")},
        "instance": {"name": "laptop-a"},
        "channels": {
            "slack": {
                "enabled": slack_enabled,
                "channel": "C0CENTRAL",
                "botTokenEnv": BOT_ENV,
                "read": {"mode": "gateway" if gateway else "poll"},
            }
        },
    }
    if gateway:
        config["gateway"] = {"url": GATEWAY_URL}
    return config


def slack_config(config) -> SlackChannelConfig:
    return SlackChannelConfig.from_mapping(config)


# -- posting_path (R4.1–R4.3) ---------------------------------------------------------------------


def test_posting_path_is_local_when_the_token_is_set_gateway_or_not(
    monkeypatch, tmp_path
):
    monkeypatch.setenv(BOT_ENV, "xoxb-local")
    for gateway in (False, True):
        config = cli_config(tmp_path, gateway=gateway)
        path = slack_mod.posting_path(slack_config(config), config)
        assert path.kind == "local" and path.detail == BOT_ENV


def test_posting_path_is_gateway_when_no_token_and_a_block_and_posting_is_on_or_unknown(
    tmp_path,
):
    config = cli_config(tmp_path, gateway=True)
    for reported in (None, "on", "unknown"):
        path = slack_mod.posting_path(
            slack_config(config), config, gateway_posting=reported
        )
        assert path.kind == "gateway" and path.detail == GATEWAY_URL, reported


def test_posting_path_is_none_with_the_reason_in_words(tmp_path):
    config = cli_config(tmp_path, gateway=False)
    path = slack_mod.posting_path(slack_config(config), config)
    assert path.kind == "none"
    assert path.detail == f"{BOT_ENV} is unset and no gateway block is configured"
    config = cli_config(tmp_path, gateway=True)
    for reported in ("disabled", "no-token", "socket-unconfigured"):
        path = slack_mod.posting_path(
            slack_config(config), config, gateway_posting=reported
        )
        assert path.kind == "none"
        assert path.detail == (
            f"{BOT_ENV} is unset and the gateway at {GATEWAY_URL} reports posting {reported}"
        )


# -- outbound_client (R4.1–R4.3) -----------------------------------------------------------------


def test_outbound_client_uses_the_local_token_first(monkeypatch, tmp_path):
    monkeypatch.setenv(BOT_ENV, "xoxb-local")
    seen = []
    config = cli_config(tmp_path, gateway=True)
    client = slack_mod.outbound_client(
        slack_config(config), config, lambda token: seen.append(token) or "sdk"
    )
    assert client == "sdk" and seen == ["xoxb-local"]


def test_outbound_client_is_the_gateway_client_without_a_token(tmp_path):
    from the_loop.channels.slack_gateway import GatewaySlackClient

    config = cli_config(tmp_path, gateway=True)
    client = slack_mod.outbound_client(slack_config(config), config)
    assert isinstance(client, GatewaySlackClient)
    assert client.url == GATEWAY_URL and client.instance == "laptop-a"


def test_outbound_client_honours_a_test_factory_on_the_gateway_path(tmp_path):
    """Every existing fake keeps working: a factory is the seam, whatever the path."""
    config = cli_config(tmp_path, gateway=True)
    client = slack_mod.outbound_client(
        slack_config(config), config, lambda token: "fake"
    )
    assert client == "fake"


def test_outbound_client_raises_todays_error_plus_the_gateway_hint(tmp_path):
    config = cli_config(tmp_path, gateway=False)
    with pytest.raises(ChannelError, match="no bot token") as info:
        slack_mod.outbound_client(slack_config(config), config)
    assert BOT_ENV in str(info.value) and "gateway" in str(info.value)
    assert "slack.post.enabled" in str(info.value)


def test_outbound_client_never_reads_the_token_variable_on_the_gateway_path(
    monkeypatch, tmp_path
):
    import os

    config = cli_config(tmp_path, gateway=True)
    reads = []
    real_get = os.environ.get

    def spying_get(key, default=None):
        reads.append(key)
        return real_get(key, default)

    monkeypatch.setattr(os.environ, "get", spying_get)
    slack_mod.outbound_client(slack_config(config), config)
    # the one read is the resolver's own "is the local token set?"; the gateway client
    # itself reads nothing
    assert reads.count(BOT_ENV) == 1


# -- the call sites (R4.2) ------------------------------------------------------------------------


def test_the_channel_loader_hands_the_channel_its_cli_config(tmp_path):
    from the_loop.channels.base import load_channels

    config = cli_config(tmp_path, gateway=True)
    (channel,) = load_channels(config)
    assert channel._cli_config == config  # noqa: SLF001


def test_the_channels_client_is_the_gateway_client_without_a_token(tmp_path):
    from the_loop.channels.base import load_channels
    from the_loop.channels.slack_gateway import GatewaySlackClient

    config = cli_config(tmp_path, gateway=True)
    (channel,) = load_channels(config)
    assert isinstance(channel._client(), GatewaySlackClient)  # noqa: SLF001
    config = cli_config(tmp_path, gateway=False)
    (channel,) = load_channels(config)
    with pytest.raises(ChannelError, match="no bot token"):
        channel._client()  # noqa: SLF001


def test_the_directory_resolves_names_through_the_gateway_client(tmp_path, monkeypatch):
    from the_loop.channels.directory import SlackDirectory
    from the_loop.channels.slack_gateway import GatewaySlackClient

    config = cli_config(tmp_path, gateway=True)
    directory = SlackDirectory(config, token_env=BOT_ENV)
    client = directory._connect()  # noqa: SLF001
    assert isinstance(client, GatewaySlackClient)
    monkeypatch.setattr(
        GatewaySlackClient,
        "conversations_list",
        lambda self, **params: {
            "ok": True,
            "channels": [{"id": "C0CENTRAL", "name": "the-loop"}],
            "response_metadata": {"next_cursor": ""},
        },
    )
    directory = SlackDirectory(config, token_env=BOT_ENV)
    assert directory.conversation_id("#the-loop") == "C0CENTRAL"


def test_the_doctors_probe_is_unverifiable_with_the_posting_paths_reason(tmp_path):
    from the_loop.channels import doctor

    config = cli_config(tmp_path, gateway=False)
    result = doctor.probe_second_consumer(config)
    assert result["verdict"] == "unverifiable"
    assert result["reason"] == f"{BOT_ENV} is unset and no gateway block is configured"
    result = doctor.check_declared_channels(config)
    assert result["reason"].startswith(f"{BOT_ENV} is unset")
    assert result["channels"][0]["status"] == "unverifiable"


def test_fetch_attachments_downloads_through_the_gateway(tmp_path, monkeypatch):
    from the_loop.channels.base import load_channels
    from the_loop.channels.slack_gateway import GatewaySlackClient

    config = cli_config(tmp_path, gateway=True)
    (channel,) = load_channels(config)
    asked = []

    def download(self, url, timeout):
        asked.append(url)
        return 200, "audio/mp4", b"\x00\x01\x02"

    monkeypatch.setattr(GatewaySlackClient, "_urllib_download", download)
    monkeypatch.setattr(
        GatewaySlackClient,
        "files_info",
        lambda self, **params: {"ok": True, "file": {"id": params["file"]}},
    )
    files = [
        {
            "id": "F1",
            "name": "clip.m4a",
            "mimetype": "audio/mp4",
            "size": 3,
            "url_private_download": "https://files.slack.com/files-pri/T1-F1/clip.m4a",
            "permalink": "https://x.slack.com/files/F1",
        }
    ]
    (attachment,) = channel.fetch_attachments(files, "github:o/r#14")
    assert attachment.error == "" and attachment.path.endswith("F1-clip.m4a")
    assert Path(attachment.path).read_bytes() == b"\x00\x01\x02"
    assert asked == ["https://files.slack.com/files-pri/T1-F1/clip.m4a"]


def test_fetch_attachments_without_any_path_is_todays_no_token(tmp_path):
    from the_loop.channels.base import load_channels

    config = cli_config(tmp_path, gateway=False)
    (channel,) = load_channels(config)
    files = [{"id": "F1", "name": "a.png", "mimetype": "image/png", "size": 1}]
    (attachment,) = channel.fetch_attachments(files, "github:o/r#14")
    assert attachment.error == "no-token"


def test_slack_attachments_treats_a_custom_fetch_as_a_credential(tmp_path):
    from the_loop.channels import attachments

    files = [
        {
            "id": "F2",
            "name": "a.png",
            "mimetype": "image/png",
            "size": 2,
            "url_private": "https://files.slack.com/files-pri/T1-F2/a.png",
        }
    ]
    out = attachments.slack_attachments(
        files, token="", dest_dir=tmp_path, fetch=lambda url, **kw: ("image/png", b"ok")
    )
    assert out[0].error == "" and out[0].path.endswith("F2-a.png")
    out = attachments.slack_attachments(files, token="", dest_dir=tmp_path / "b")
    assert out[0].error == "no-token"
