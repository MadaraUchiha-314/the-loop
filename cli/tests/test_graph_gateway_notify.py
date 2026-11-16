"""Unit tests for issue-532 (T1/T8 — R1.1, R1.2, R1.4, R2.1): the config
``build_runtime`` hands every graph runtime carries the ``gateway`` and ``instance``
blocks, so a graph hook's first Slack post on a gateway consumer resolves the gateway
path instead of failing with "no bot token".

Run with: pytest (from the cli/ directory).
"""

from __future__ import annotations

import pytest

from the_loop.channels import slack as slack_mod
from the_loop.channels.slack import SlackChannelConfig
from the_loop.cli_config import instance_name
from the_loop.graph import bootstrap

BOT_ENV = "THE_LOOP_TEST_532_BOT_TOKEN"
GATEWAY_URL = "http://127.0.0.1:8799"


@pytest.fixture(autouse=True)
def _no_token(monkeypatch):
    monkeypatch.delenv(BOT_ENV, raising=False)


def _cli(tmp_path, *, gateway=True):
    cli = {
        "state": {"root": str(tmp_path / "state")},
        "instance": {"name": "laptop-a"},
        "channels": {
            "slack": {
                "enabled": True,
                "channel": "C0CENTRAL",
                "botTokenEnv": BOT_ENV,
                "read": {"mode": "gateway"},
            }
        },
    }
    if gateway is True:
        cli["gateway"] = {"url": GATEWAY_URL}
    elif gateway is not False:
        cli["gateway"] = gateway
    return cli


def _runtime_config(tmp_path, monkeypatch, cli):
    monkeypatch.setattr(bootstrap, "load_cli_config_best_effort", lambda: cli)
    return bootstrap.build_runtime(tmp_path).config


def _path(config):
    return slack_mod.posting_path(SlackChannelConfig.from_mapping(config), config)


def test_the_runtime_config_carries_the_gateway_block(tmp_path, monkeypatch):
    """R1.1: a graph runtime's config resolves the gateway path with no token."""
    config = _runtime_config(tmp_path, monkeypatch, _cli(tmp_path))
    assert config["gateway"] == {"url": GATEWAY_URL}
    path = _path(config)
    assert path.kind == "gateway" and path.detail == GATEWAY_URL


def test_the_runtime_config_carries_the_instance_name(tmp_path, monkeypatch):
    """R1.2: the gateway client built from it calls under this instance's name."""
    config = _runtime_config(tmp_path, monkeypatch, _cli(tmp_path))
    assert instance_name(config) == "laptop-a"


@pytest.mark.parametrize("gateway", [False, None, "not-a-mapping", {"url": ""}])
def test_no_usable_gateway_block_still_resolves_no_gateway(
    tmp_path, monkeypatch, gateway
):
    """R1.4 / T8: absent or malformed stays fail-closed — today's `none` path."""
    config = _runtime_config(tmp_path, monkeypatch, _cli(tmp_path, gateway=gateway))
    assert _path(config).kind == "none"
