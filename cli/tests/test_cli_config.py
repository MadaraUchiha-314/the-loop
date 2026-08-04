"""Unit tests for the CLI config resolution/loading (issue-63, decision-032).

Run with: pytest (from the cli/ directory).
"""

import logging
from pathlib import Path

import pytest

from the_loop import cli_config


@pytest.fixture(autouse=True)
def _no_leaked_override():
    """--config is a module-level override (cli.py's pre-scan); never let one
    test's cli_config.set_override() leak into the next."""
    cli_config.set_override(None)
    yield
    cli_config.set_override(None)


@pytest.fixture()
def isolated_cwd(tmp_path, monkeypatch):
    """A cwd with no .the-loop/cli-config.yaml of its own (this repo's real
    one — checked in for dogfooding — must not leak into these tests)."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


# -- priority order: --config > $THE_LOOP_CLI_CONFIG > cwd > home ---------------


def test_home_default_when_nothing_else_is_set(monkeypatch, isolated_cwd):
    monkeypatch.delenv(cli_config.CLI_CONFIG_ENV, raising=False)
    home = isolated_cwd / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    assert (
        cli_config.default_cli_config_path() == home / ".the-loop" / "cli-config.yaml"
    )


def test_cwd_file_wins_over_home_default(monkeypatch, isolated_cwd):
    monkeypatch.delenv(cli_config.CLI_CONFIG_ENV, raising=False)
    monkeypatch.setattr(Path, "home", lambda: isolated_cwd / "home")
    cwd_cfg_dir = isolated_cwd / ".the-loop"
    cwd_cfg_dir.mkdir()
    (cwd_cfg_dir / "cli-config.yaml").write_text("version: '0.1.0'\n")
    assert cli_config.default_cli_config_path() == Path(".the-loop/cli-config.yaml")


def test_cwd_file_absent_falls_through_to_home(monkeypatch, isolated_cwd):
    monkeypatch.delenv(cli_config.CLI_CONFIG_ENV, raising=False)
    home = isolated_cwd / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    # no .the-loop/cli-config.yaml created under isolated_cwd
    assert (
        cli_config.default_cli_config_path() == home / ".the-loop" / "cli-config.yaml"
    )


def test_env_var_wins_over_cwd_file(monkeypatch, isolated_cwd):
    cwd_cfg_dir = isolated_cwd / ".the-loop"
    cwd_cfg_dir.mkdir()
    (cwd_cfg_dir / "cli-config.yaml").write_text("version: '0.1.0'\n")
    override = isolated_cwd / "elsewhere.yaml"
    monkeypatch.setenv(cli_config.CLI_CONFIG_ENV, str(override))
    assert cli_config.default_cli_config_path() == override


def test_explicit_override_wins_over_everything(monkeypatch, isolated_cwd):
    cwd_cfg_dir = isolated_cwd / ".the-loop"
    cwd_cfg_dir.mkdir()
    (cwd_cfg_dir / "cli-config.yaml").write_text("version: '0.1.0'\n")
    monkeypatch.setenv(cli_config.CLI_CONFIG_ENV, str(isolated_cwd / "env.yaml"))
    explicit = isolated_cwd / "flag.yaml"
    cli_config.set_override(explicit)
    assert cli_config.default_cli_config_path() == explicit


def test_set_override_none_clears_it(isolated_cwd):
    cli_config.set_override(isolated_cwd / "flag.yaml")
    cli_config.set_override(None)
    assert cli_config.default_cli_config_path() != isolated_cwd / "flag.yaml"


# -- load_cli_config: lenient vs strict ------------------------------------------


def test_missing_file_lenient_empty_strict_raises(tmp_path):
    missing = tmp_path / "config.yaml"
    assert cli_config.load_cli_config(missing, strict=False) == {}
    with pytest.raises(FileNotFoundError):
        cli_config.load_cli_config(missing, strict=True)


def test_unparseable_yaml_lenient_empty_strict_raises(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("webhooks: [unclosed\n")
    assert cli_config.load_cli_config(cfg, strict=False) == {}
    with pytest.raises(Exception):
        cli_config.load_cli_config(cfg, strict=True)


def test_valid_yaml_parses_full_document(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "webhooks:\n  ghWebhook:\n    port: 9999\npolling:\n  intervalSeconds: 5\n"
    )
    data = cli_config.load_cli_config(cfg)
    assert data["webhooks"]["ghWebhook"]["port"] == 9999
    assert data["polling"]["intervalSeconds"] == 5


def test_empty_file_is_empty_mapping(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("")
    assert cli_config.load_cli_config(cfg, strict=False) == {}
    assert cli_config.load_cli_config(cfg, strict=True) == {}


# -- module-level command wiring -------------------------------------------------


def test_gh_webhook_and_poll_default_to_the_cli_config_path():
    """gh_webhook._CONFIG_PATH and poll._CONFIG_PATH are the CLI config — the
    ONLY config either reads (issue-63 review: no plugin-config fallback) —
    at import time."""
    from the_loop.commands import gh_webhook, poll

    assert gh_webhook._CONFIG_PATH == cli_config.default_cli_config_path()
    assert poll._CONFIG_PATH == cli_config.default_cli_config_path()
    assert not hasattr(gh_webhook, "_PLUGIN_CONFIG_PATH")
    assert not hasattr(poll, "_PLUGIN_CONFIG_PATH")


# -- the shared routing accessor (issue-142) -------------------------------------


def test_routing_is_read_from_the_top_level_key(tmp_path):
    """`routing` governs BOTH ingresses, so it is read from the top level."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("routing:\n  enabled: true\n  authorizedUsers: [operator]\n")
    assert cli_config.load_routing_config(cfg) == {
        "enabled": True,
        "authorizedUsers": ["operator"],
    }


def test_a_config_without_routing_reads_as_an_empty_policy(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("webhooks:\n  ghWebhook:\n    port: 9999\n")
    assert cli_config.load_routing_config(cfg) == {}
    assert cli_config.load_routing_config(tmp_path / "absent.yaml") == {}


def test_the_accessor_resolves_the_config_path_per_call(monkeypatch, isolated_cwd):
    """No cached module global: `--config` is honoured whenever it was set."""
    cfg = isolated_cwd / "flag.yaml"
    cfg.write_text("routing:\n  spawnOnUnmatched: always\n")
    monkeypatch.delenv(cli_config.CLI_CONFIG_ENV, raising=False)
    cli_config.set_override(cfg)
    assert cli_config.load_routing_config() == {"spawnOnUnmatched": "always"}


def test_the_gh_binary_reaches_the_promoted_block(tmp_path):
    """`integrations.github.cli.binary` still fans out to the three features."""
    config = cli_config.apply_integrations(
        {
            "integrations": {"github": {"cli": {"binary": "gh-enterprise"}}},
            "routing": {"control": {}, "reactions": {}, "announce": {}},
        }
    )
    for feature in ("control", "reactions", "announce"):
        assert config["routing"][feature]["_ghBinary"] == "gh-enterprise"


def test_the_poller_and_sessions_no_longer_read_routing_through_the_receiver():
    """The import seam issue-142 removed: `routing` is nobody's private block.

    A reader auditing which logins may drive their daemon should find
    `authorizedUsers` resolved by one shared accessor, not by importing the
    webhook command's module.
    """
    from the_loop.commands import poll, sessions_cmd

    for module in (poll, sessions_cmd):
        assert not hasattr(module, "_load_config_defaults")


def test_eventlog_load_config_reads_top_level_event_log_key(tmp_path):
    from the_loop import eventlog

    cfg = tmp_path / "config.yaml"
    cfg.write_text("eventLog:\n  enabled: false\n  path: custom.jsonl\n")
    assert eventlog.load_config(cfg) == {"enabled": False, "path": "custom.jsonl"}


def test_eventlog_load_config_defaults_to_cli_config_path(monkeypatch, tmp_path):
    from the_loop import eventlog

    cfg_dir = tmp_path / ".the-loop"
    cfg_dir.mkdir()
    cfg = cfg_dir / "config.yaml"
    cfg.write_text("eventLog:\n  enabled: false\n")
    monkeypatch.setenv(cli_config.CLI_CONFIG_ENV, str(cfg))
    assert eventlog.load_config() == {"enabled": False}


# -- cli.py: --config flag pre-scan + refresh ------------------------------------


def test_config_flag_overrides_resolved_path_for_defaults(monkeypatch, isolated_cwd):
    """`the-loop --config X gh-webhook start` computes --host/--port/etc.
    defaults from X, not the CWD/home/env resolution."""
    from the_loop.cli import build_parser, main

    monkeypatch.delenv(cli_config.CLI_CONFIG_ENV, raising=False)
    cfg = isolated_cwd / "custom.yaml"
    cfg.write_text("webhooks:\n  ghWebhook:\n    port: 9191\n")

    # main() pre-scans --config and refreshes gh_webhook/poll._CONFIG_PATH
    # before build_parser() computes their other flags' defaults.
    with pytest.raises(SystemExit) as exc:
        main(["--config", str(cfg), "--version"])
    assert exc.value.code == 0  # sanity: main() ran the pre-scan without error

    parser = build_parser()
    args = parser.parse_args(["gh-webhook", "start"])
    assert args.port == 9191


def test_no_config_flag_leaves_resolution_at_cwd_or_home(monkeypatch, isolated_cwd):
    from the_loop.cli import main

    monkeypatch.delenv(cli_config.CLI_CONFIG_ENV, raising=False)
    home = isolated_cwd / "home"
    monkeypatch.setattr(Path, "home", lambda: home)

    with pytest.raises(SystemExit):
        main(["--version"])
    assert cli_config._override is None


# -- webhook event filter defaults + lifecycle warning (issue-94) --------------


def test_events_defaults_to_the_routable_set_including_lifecycle_events():
    from the_loop.commands.gh_webhook import DEFAULT_EVENTS, resolve_events

    for config in ({}, {"events": []}, {"events": None}):
        events = resolve_events(config)
        assert events == DEFAULT_EVENTS
        # the two that make a finished work item close its session
        assert "issues" in events and "pull_request" in events


def test_an_explicit_events_list_still_wins():
    from the_loop.commands.gh_webhook import resolve_events

    assert resolve_events({"events": ["issues"]}) == ["issues"]


def test_an_events_list_without_the_lifecycle_events_warns(caplog):
    from the_loop.commands.gh_webhook import warn_on_missing_lifecycle_events

    with caplog.at_level(logging.WARNING, logger="the-loop.gh-webhook"):
        missing = warn_on_missing_lifecycle_events(["issue_comment", "workflow_run"])
    assert missing == ["issues", "pull_request"]
    assert "never reach the receiver" in caplog.text


def test_the_default_set_warns_about_nothing(caplog):
    from the_loop.commands.gh_webhook import (
        DEFAULT_EVENTS,
        warn_on_missing_lifecycle_events,
    )

    with caplog.at_level(logging.WARNING, logger="the-loop.gh-webhook"):
        assert warn_on_missing_lifecycle_events(DEFAULT_EVENTS) == []
    assert caplog.text == ""
