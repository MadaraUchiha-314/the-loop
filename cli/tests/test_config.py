"""Unit tests for CLI config resolution (issue #63 — CLI/plugin config split).

Covers the user/machine-level CLI config location, the ``$THE_LOOP_CLI_CONFIG``
override, and the backward-compatible fallback to the legacy per-repo
``.the-loop/config.yaml`` ``webhooks`` block. Run with: pytest (from cli/).
"""

import pytest

from the_loop import config as cfg

# The whole point of the split is reading YAML config, so skip cleanly when the
# optional dependency is absent rather than asserting built-in defaults.
pytest.importorskip("yaml")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_cli_config_path_prefers_explicit_override(monkeypatch, tmp_path):
    target = tmp_path / "custom" / "cli.yaml"
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(target))
    assert cfg.cli_config_path() == target


def test_cli_config_path_uses_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.delenv("THE_LOOP_CLI_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert cfg.cli_config_path() == tmp_path / "the-loop" / "config.yaml"


def test_cli_config_path_defaults_to_home_config(monkeypatch, tmp_path):
    monkeypatch.delenv("THE_LOOP_CLI_CONFIG", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(cfg.Path, "home", staticmethod(lambda: tmp_path))
    assert cfg.cli_config_path() == tmp_path / ".config" / "the-loop" / "config.yaml"


def test_load_gh_webhook_config_reads_cli_config(monkeypatch, tmp_path):
    cli_cfg = tmp_path / "cli.yaml"
    _write(cli_cfg, "webhooks:\n  ghWebhook:\n    port: 9999\n")
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(cli_cfg))
    assert cfg.load_gh_webhook_config().get("port") == 9999


def test_load_gh_webhook_config_falls_back_to_legacy_repo_config(
    monkeypatch, tmp_path, caplog
):
    # No CLI config present, but a legacy per-repo .the-loop/config.yaml is.
    missing = tmp_path / "does-not-exist.yaml"
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(missing))

    repo = tmp_path / "repo"
    _write(repo / ".the-loop" / "config.yaml", "webhooks:\n  ghWebhook:\n    port: 7777\n")
    monkeypatch.chdir(repo)

    with caplog.at_level("WARNING"):
        result = cfg.load_gh_webhook_config()
    assert result.get("port") == 7777
    assert any("legacy" in r.message for r in caplog.records)


def test_load_gh_webhook_config_returns_empty_when_nothing_present(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "nope.yaml"))
    monkeypatch.chdir(tmp_path)  # no .the-loop/config.yaml here either
    assert cfg.load_gh_webhook_config() == {}


def test_cli_config_wins_over_legacy_when_both_present(monkeypatch, tmp_path):
    cli_cfg = tmp_path / "cli.yaml"
    _write(cli_cfg, "webhooks:\n  ghWebhook:\n    port: 1111\n")
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(cli_cfg))

    repo = tmp_path / "repo"
    _write(repo / ".the-loop" / "config.yaml", "webhooks:\n  ghWebhook:\n    port: 2222\n")
    monkeypatch.chdir(repo)

    assert cfg.load_gh_webhook_config().get("port") == 1111
