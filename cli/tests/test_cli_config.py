"""Unit tests for the CLI config resolution/loading (issue-63, decision-032).

Run with: pytest (from the cli/ directory).
"""

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
    """gh_webhook._CONFIG_PATH and poll._CONFIG_PATH are the CLI config — not
    the repo-local PLUGIN config (.the-loop/config.yaml) — at import time."""
    from the_loop.commands import gh_webhook, poll

    assert gh_webhook._CONFIG_PATH == cli_config.default_cli_config_path()
    assert poll._CONFIG_PATH == cli_config.default_cli_config_path()
    assert gh_webhook._PLUGIN_CONFIG_PATH == Path(".the-loop/config.yaml")
    assert poll._PLUGIN_CONFIG_PATH == Path(".the-loop/config.yaml")


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
