"""Scenario tests for the env file the CLI config names (issue-318, T2)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from the_loop import cli, cli_config

TOKEN_VAR = "THE_LOOP_SLACK_BOT_TOKEN"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv(TOKEN_VAR, raising=False)
    cli_config.set_override(None)
    yield
    cli_config.set_override(None)


def _operator_setup(tmp_path: Path) -> Path:
    home = tmp_path / ".the-loop"
    home.mkdir()
    (home / ".env").write_text(f"export {TOKEN_VAR}='xoxb-test-000000000000'\n")
    config = home / "cli-config.yaml"
    config.write_text(
        "version: '0.7.0'\n"
        "env:\n"
        "  file: .env\n"
        "channels:\n"
        "  slack:\n"
        "    enabled: false\n"
        f"    botTokenEnv: {TOKEN_VAR}\n"
    )
    return config


def test_the_slack_token_comes_from_the_env_file_the_config_names(
    tmp_path: Path, monkeypatch
):
    """
    Feature: the CLI loads an env file the CLI config names, at start
      Scenario: The Slack token comes from the env file the config names
        Given a CLI config at ~/.the-loop/cli-config.yaml naming env.file: .env
        And ~/.the-loop/.env declaring the variable channels.slack.botTokenEnv names
        And the variable is not set in the shell
        When the-loop is run from an unrelated working directory
        Then the variable is in the process environment before any command runs
        And nothing was written to the config or the working directory

    Requirement: docs/specs/issue-318/requirements.md R1.2, R1.3, R1.6
    """
    config = _operator_setup(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    with pytest.raises(SystemExit) as stop:
        cli.main(["--config", str(config), "--version"])
    assert stop.value.code == 0
    assert os.environ[TOKEN_VAR] == "xoxb-test-000000000000"
    assert sorted(p.name for p in elsewhere.iterdir()) == []
    assert config.read_text().count("xoxb") == 0


def test_an_exported_token_survives_the_env_file(tmp_path: Path, monkeypatch):
    """
    Feature: the CLI loads an env file the CLI config names, at start
      Scenario: A token exported in the shell wins over the file
        Given the same config and env file
        And the variable already exported with a different value
        When the-loop is run
        Then the exported value is untouched

    Requirement: docs/specs/issue-318/requirements.md R1.5
    """
    config = _operator_setup(tmp_path)
    monkeypatch.setenv(TOKEN_VAR, "xoxb-exported")
    with pytest.raises(SystemExit):
        cli.main(["--config", str(config), "--version"])
    assert os.environ[TOKEN_VAR] == "xoxb-exported"
