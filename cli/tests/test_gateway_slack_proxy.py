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


def test_config_without_slack_post_reads_posting_on(tmp_path):
    """A 20.9.0 file has no `slack.post`; it validates and posting defaults to on
    (R6.1, T10 migration)."""
    conf = gwconfig.load_gateway_config(_write(tmp_path, {**MINIMAL, "slack": SLACK}))
    assert conf.slack is not None
    assert conf.slack.post.enabled is True


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
