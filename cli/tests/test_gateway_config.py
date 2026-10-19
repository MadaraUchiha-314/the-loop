"""Unit tests for ``gateway-config.yaml`` and the instance's ``gateway`` block
(issue-496, T1 — R8.1, R8.2, R8.7; abuse case 7).

Run with: pytest (from the cli/ directory).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from the_loop import configschema
from the_loop.gateway import config as gwconfig

ENV_NAME = "THE_LOOP_TEST_GATEWAY_TOKEN"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv(ENV_NAME, raising=False)
    monkeypatch.delenv(gwconfig.GATEWAY_CONFIG_ENV, raising=False)
    gwconfig.set_override(None)
    yield
    gwconfig.set_override(None)


def _write(tmp_path: Path, body: dict, name: str = "gateway-config.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(body), encoding="utf-8")
    return path


MINIMAL = {"version": "1", "listen": {"host": "127.0.0.1", "port": 8790}}


# -- a valid file loads with the design's defaults (R8.2, R14.2) ----------------------------


def test_a_minimal_file_loads_with_the_designs_defaults(tmp_path):
    path = _write(tmp_path, MINIMAL)
    conf = gwconfig.load_gateway_config(path)
    assert conf.listen.port == 8790
    assert conf.listen.exposed is False
    assert conf.store.retention_days == 7
    assert conf.store.max_attempts == 3
    assert conf.consume.max_batch == 256
    assert conf.consume.max_wait_s == 30
    assert conf.consume.lease_s == (10, 300)
    assert conf.github is None and conf.jira is None and conf.slack is None
    assert conf.instances is None
    assert conf.state_root == Path("~/.the-loop/gateway").expanduser().resolve()
    assert conf.store.path == conf.state_root / "gateway.db"
    assert conf.event_log == conf.state_root / "logs" / "events.jsonl"
    assert conf.pidfile == conf.state_root / "gateway.pid"


def test_a_relative_state_root_resolves_against_the_config_file(tmp_path):
    path = _write(tmp_path, {**MINIMAL, "state": {"root": "gw-state"}})
    conf = gwconfig.load_gateway_config(path)
    assert conf.state_root == tmp_path / "gw-state"
    assert conf.store.path == tmp_path / "gw-state" / "gateway.db"


def test_the_template_is_valid_and_types_every_block(tmp_path):
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
    assert conf.github is not None and conf.github.poll.enabled is True
    assert conf.github.webhook.enabled is False
    assert conf.slack is not None and conf.slack.socket.enabled is True
    assert conf.slack.http.enabled is False
    assert conf.jira is not None and conf.jira.poll.enabled is False
    assert conf.secret_names() == sorted(
        {
            "THE_LOOP_GH_WEBHOOK_SECRET",
            "GITHUB_TOKEN",
            "THE_LOOP_JIRA_WEBHOOK_SECRET",
            "THE_LOOP_JIRA_EMAIL",
            "THE_LOOP_JIRA_TOKEN",
            "THE_LOOP_SLACK_APP_TOKEN",
            "THE_LOOP_SLACK_BOT_TOKEN",
            "SLACK_SIGNING_SECRET",
        }
    )


def test_poll_sources_and_rooms_are_typed(tmp_path):
    body = {
        **MINIMAL,
        "repositories": ["o/r"],
        "github": {
            "poll": {
                "sources": [{"repository": "o/r", "labels": ["the-loop: auto-execute"]}]
            }
        },
        "slack": {"rooms": [{"channel": "C1", "workItem": "github:o/r#1"}]},
        "instances": ["laptop-a", "laptop-b"],
    }
    conf = gwconfig.load_gateway_config(_write(tmp_path, body))
    assert conf.github is not None
    (source,) = conf.github.poll.sources
    assert source.repository == "o/r"
    assert source.labels == ("the-loop: auto-execute",)
    assert source.issues is True and source.pull_requests is True
    assert conf.slack is not None
    assert conf.slack.rooms[0].work_item == "github:o/r#1"
    assert conf.instances == ("laptop-a", "laptop-b")


# -- violations name the path (R8.1) ---------------------------------------------------------


def test_a_missing_file_is_a_config_error_naming_the_path(tmp_path):
    missing = tmp_path / "nope.yaml"
    with pytest.raises(gwconfig.ConfigError) as info:
        gwconfig.load_gateway_config(missing)
    assert str(missing) in str(info.value)


def test_a_wrong_type_fails_naming_the_key_path(tmp_path):
    path = _write(tmp_path, {"listen": {"host": "127.0.0.1", "port": "eighty"}})
    with pytest.raises(gwconfig.ConfigError) as info:
        gwconfig.load_gateway_config(path)
    assert any(error.startswith("listen.port") for error in info.value.errors), (
        info.value.errors
    )


def test_an_unknown_key_fails_naming_it(tmp_path):
    path = _write(tmp_path, {**MINIMAL, "listne": {"port": 1}})
    with pytest.raises(gwconfig.ConfigError) as info:
        gwconfig.load_gateway_config(path)
    assert any("listne" in error for error in info.value.errors)


def test_every_violation_is_reported_at_once(tmp_path):
    path = _write(
        tmp_path,
        {"listen": {"port": 0}, "store": {"retentionDays": 0}, "nonsense": True},
    )
    with pytest.raises(gwconfig.ConfigError) as info:
        gwconfig.load_gateway_config(path)
    assert len(info.value.errors) >= 3


# -- abuse case 7: a pasted token fails validation naming the key -------------------------


@pytest.mark.parametrize(
    "block,key_path",
    [
        (
            {"slack": {"socket": {"appTokenEnv": "xapp-1-A0-123-abc"}}},
            "slack.socket.appTokenEnv",
        ),
        (
            {"slack": {"socket": {"botTokenEnv": "xoxb-123-abc"}}},
            "slack.socket.botTokenEnv",
        ),
        (
            {"github": {"webhook": {"secretEnv": "s3cret-value"}}},
            "github.webhook.secretEnv",
        ),
        ({"github": {"poll": {"tokenEnv": "ghp_abcDEF"}}}, "github.poll.tokenEnv"),
        ({"jira": {"poll": {"tokenEnv": "ATATT3x"}}}, "jira.poll.tokenEnv"),
        (
            {"slack": {"http": {"signingSecretEnv": "a1b2c3"}}},
            "slack.http.signingSecretEnv",
        ),
    ],
)
def test_a_config_with_a_pasted_token_fails_validation_naming_the_key(
    tmp_path, block, key_path
):
    """
    Feature: secrets are named, never written (requirements §Security, abuse case 7)
      Scenario: a config with a pasted token fails validation naming the key
        Given a gateway-config.yaml whose *Env key holds a token value
        When the gateway loads it
        Then it is refused, and the message names the key but not the value's shape

    Requirement: docs/specs/issue-496/requirements.md#requirement-8 (R8.2)
    """
    path = _write(tmp_path, {**MINIMAL, **block})
    with pytest.raises(gwconfig.ConfigError) as info:
        gwconfig.load_gateway_config(path)
    assert any(error.startswith(key_path) for error in info.value.errors), (
        info.value.errors
    )


def test_a_variable_name_with_a_lowercase_character_fails(tmp_path):
    path = _write(
        tmp_path, {**MINIMAL, "github": {"poll": {"tokenEnv": "Github_Token"}}}
    )
    with pytest.raises(gwconfig.ConfigError):
        gwconfig.load_gateway_config(path)


# -- env.file: loaded first, relative to the file, never overwriting (R8.2, issue-318) ------


def test_the_env_file_is_resolved_against_the_config_and_loaded_without_overwriting(
    tmp_path, monkeypatch
):
    (tmp_path / "gw.env").write_text(f"{ENV_NAME}=from-file\nOTHER_GW_TEST=x\n")
    path = _write(tmp_path, {**MINIMAL, "env": {"file": "gw.env"}})
    conf = gwconfig.load_gateway_config(path)
    assert conf.env_file == tmp_path / "gw.env"

    monkeypatch.setenv(ENV_NAME, "already-set")
    monkeypatch.delenv("OTHER_GW_TEST", raising=False)
    result = gwconfig.load_gateway_env_file(path)
    assert result is not None
    assert os.environ[ENV_NAME] == "already-set"
    assert os.environ["OTHER_GW_TEST"] == "x"
    monkeypatch.delenv("OTHER_GW_TEST", raising=False)


def test_a_missing_env_file_is_a_warning_naming_the_path_not_an_error(tmp_path, caplog):
    path = _write(tmp_path, {**MINIMAL, "env": {"file": "absent.env"}})
    with caplog.at_level("WARNING"):
        assert gwconfig.load_gateway_env_file(path) is None
    assert "absent.env" in caplog.text
    # and the config itself still loads: a missing env file never blocks a start
    gwconfig.load_gateway_config(path)


def test_an_unset_env_file_loads_nothing(tmp_path):
    path = _write(tmp_path, MINIMAL)
    assert gwconfig.load_gateway_env_file(path) is None


# -- resolution order mirrors the CLI config (design §gateway/config.py) ----------------------


def test_the_path_resolves_override_then_env_then_cwd_then_home(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert gwconfig.default_gateway_config_path() == (
        Path.home() / ".the-loop" / gwconfig.GATEWAY_CONFIG_FILENAME
    )
    (tmp_path / ".the-loop").mkdir()
    cwd_file = tmp_path / ".the-loop" / gwconfig.GATEWAY_CONFIG_FILENAME
    cwd_file.write_text("version: '1'\n")
    assert gwconfig.default_gateway_config_path() == Path(".the-loop") / (
        gwconfig.GATEWAY_CONFIG_FILENAME
    )
    monkeypatch.setenv(gwconfig.GATEWAY_CONFIG_ENV, str(tmp_path / "env.yaml"))
    assert gwconfig.default_gateway_config_path() == tmp_path / "env.yaml"
    gwconfig.set_override(tmp_path / "flag.yaml")
    assert gwconfig.default_gateway_config_path() == tmp_path / "flag.yaml"


def test_the_packaged_schema_resolves_and_is_an_object_schema():
    schema = configschema.load_schema("gateway-config")
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "consume" in schema["properties"]


# -- the instance's `gateway` block (R4.2, R8.7) ---------------------------------------------


def _cli(body: dict) -> list:
    return configschema.validate(body, configschema.load_schema("cli-config"))


def test_a_block_with_only_url_validates_and_carries_the_defaults():
    from the_loop import cli_config

    assert _cli({"gateway": {"url": "http://127.0.0.1:8790"}}) == []
    block = cli_config.gateway_block({"gateway": {"url": "http://127.0.0.1:8790/"}})
    assert block is not None
    assert block.url == "http://127.0.0.1:8790"
    assert block.poll_interval_s == 5
    assert block.long_poll_s == 20
    assert block.actors == {"github": (), "slack": (), "jira": ()}
    assert block.lease_s == 3 * 5 + 20


def test_a_block_without_url_fails_validation_and_types_to_none(caplog):
    from the_loop import cli_config

    errors = _cli({"gateway": {"pollIntervalSeconds": 5}})
    assert any(error.startswith("gateway") and "url" in error for error in errors)
    with caplog.at_level("WARNING"):
        assert cli_config.gateway_block({"gateway": {"pollIntervalSeconds": 5}}) is None
    assert "gateway.url" in caplog.text


def test_the_block_types_actors_and_the_polling_mode():
    from the_loop import cli_config

    body = {
        "gateway": {
            "url": "http://gw.internal:8790",
            "pollIntervalSeconds": 2,
            "longPollSeconds": 0,
            "actors": {"github": ["octocat"], "slack": ["U0123"]},
        }
    }
    assert _cli(body) == []
    block = cli_config.gateway_block(body)
    assert block is not None
    assert block.poll_interval_s == 2 and block.long_poll_s == 0
    assert block.actors == {"github": ("octocat",), "slack": ("U0123",), "jira": ()}


def test_an_unknown_gateway_key_and_a_bad_url_are_refused():
    assert any(
        "gateway" in e for e in _cli({"gateway": {"url": "http://x", "stream": 1}})
    )
    assert any(
        "gateway.url" in e for e in _cli({"gateway": {"url": "gw.internal:8790"}})
    )


def test_no_block_means_no_gateway():
    from the_loop import cli_config

    assert cli_config.gateway_block({}) is None
    assert cli_config.gateway_block(None) is None
    assert cli_config.gateway_block({"gateway": None}) is None


def test_instance_name_defaults_to_default():
    from the_loop import cli_config

    assert cli_config.instance_name({}) == "default"
    assert cli_config.instance_name({"instance": {"name": ""}}) == "default"
    assert cli_config.instance_name({"instance": {"name": "laptop-a"}}) == "laptop-a"


def test_the_repositorys_own_config_still_validates_without_a_block():
    repo_config = Path(__file__).resolve().parents[2] / ".the-loop" / "cli-config.yaml"
    if not repo_config.is_file():
        pytest.skip("plugin tree not present (source distribution)")
    assert _cli(yaml.safe_load(repo_config.read_text())) == []
