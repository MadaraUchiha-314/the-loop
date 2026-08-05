"""End-to-end: `the-loop install` / `the-loop upgrade` (issue-152).

These drive the *registered commands* through ``the_loop.cli.main`` — argv in, rendered
report on stdout, process exit code out — against a machine made of **fake binaries** on
a temporary ``PATH`` and a fake ``HOME``. That is what the unit tests cannot prove: that
the verbs are wired into the CLI, that the harness surface is probed off a real
executable, and that what lands on disk is what the plan said it would be.

Every test drives a fake HOME, because the file under test would otherwise be the
developer's own ``~/.claude/settings.json``.

Feature: Installing and upgrading the-loop from its own CLI
Requirement: docs/specs/issue-152/requirements.md
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from the_loop.cli import main
from the_loop.harness_plugins import MARKETPLACE_NAME, PLUGIN_KEY

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="the fake binaries are POSIX shell scripts"
)


def _script(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def fake_harness(
    bin_dir: Path, name: str, log: Path, *, scope: bool = True, exit_code: int = 0
) -> Path:
    """A binary that answers `plugin --help` the way a plugin-aware harness does."""
    scope_help = "  -s, --scope <scope>" if scope else "  -h, --help"
    return _script(
        bin_dir / name,
        f"""
if [ "$1" = "plugin" ] && [ "$2" = "--help" ]; then
  echo "Commands:"; echo "  marketplace  Manage marketplaces"; echo "  install"; exit 0
fi
if [ "$1" = "plugin" ] && [ "$2" = "install" ] && [ "$3" = "--help" ]; then
  echo "Options:"; echo "{scope_help}"; exit 0
fi
echo "$@" >> "{log}"
if [ "$2" = "install" ] || [ "$2" = "update" ]; then exit {exit_code}; fi
exit 0
""",
    )


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """An empty machine: a fake HOME, an empty PATH, and a command log."""
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    # Keep the CLI config resolution off the developer's real ~/.the-loop.
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "absent-cli-config.yaml"))
    return {"home": home, "bin": bin_dir, "log": tmp_path / "commands.log"}


def test_install_drives_the_harnesss_own_plugin_cli(machine, capsys):
    """
    Scenario: A machine with a plugin-aware Claude Code
      Given `claude` on PATH exposing `plugin marketplace` and `--scope`
      When the operator runs `the-loop install claude`
      Then the-loop runs that binary's marketplace-add and plugin-install commands
      And it writes no settings file of its own
      And the process exits 0
    """
    fake_harness(machine["bin"], "claude", machine["log"])

    code = main(["install", "claude", "--from", "acme/loop"])

    assert code == 0
    ran = machine["log"].read_text(encoding="utf-8").splitlines()
    assert ran == [
        "plugin marketplace add acme/loop --scope user",
        f"plugin install {PLUGIN_KEY} --scope user",
    ]
    assert not (machine["home"] / ".claude" / "settings.json").exists()
    assert "applied" in capsys.readouterr().out


def test_upgrade_refreshes_the_marketplace_then_updates_the_plugin(machine, capsys):
    """
    Scenario: Moving an installed plugin to the current release
      Given `claude` on PATH exposing a plugin surface
      When the operator runs `the-loop upgrade claude`
      Then the marketplace is refreshed before the plugin is updated
      And the process exits 0
    """
    fake_harness(machine["bin"], "claude", machine["log"])

    assert main(["upgrade", "claude"]) == 0

    assert machine["log"].read_text(encoding="utf-8").splitlines() == [
        f"plugin marketplace update {MARKETPLACE_NAME}",
        f"plugin update {PLUGIN_KEY} --scope user",
    ]


def test_without_a_plugin_cli_the_settings_fallback_is_used_and_is_idempotent(
    machine, capsys
):
    """
    Scenario: A machine whose Claude Code build has no `plugin` command
      Given no `claude` binary on PATH
      When the operator runs `the-loop install claude` twice
      Then the first run writes the marketplace and enabled-plugin keys
      And the second run reports `already` and rewrites nothing
    """
    assert main(["install", "claude"]) == 0
    settings = machine["home"] / ".claude" / "settings.json"
    written = json.loads(settings.read_text(encoding="utf-8"))
    assert written["enabledPlugins"][PLUGIN_KEY] is True
    stamp = settings.stat().st_mtime_ns
    capsys.readouterr()

    assert main(["install", "claude"]) == 0

    assert "already" in capsys.readouterr().out
    assert settings.stat().st_mtime_ns == stamp


def test_project_scope_writes_the_projects_settings_not_the_users(machine, tmp_path):
    """
    Scenario: Trying the-loop out on one repository only
      Given no harness CLI on PATH
      When the operator runs `the-loop install claude --scope project --project-dir <repo>`
      Then the repository's own .claude/settings.json carries the plugin
      And the user's settings file is untouched
    """
    project = tmp_path / "repo"
    project.mkdir()

    assert (
        main(["install", "claude", "--scope", "project", "--project-dir", str(project)])
        == 0
    )

    assert (project / ".claude" / "settings.json").is_file()
    assert not (machine["home"] / ".claude" / "settings.json").exists()


def test_a_scope_that_cannot_be_expressed_is_skipped_never_widened(machine, capsys):
    """
    Scenario: A harness CLI that manages plugins but knows no scopes
      Given `claude` on PATH whose `plugin install` help has no --scope
      When the operator asks for a project-scoped install
      Then the component is reported skipped with the reason
      And nothing is installed at user scope instead
    """
    fake_harness(machine["bin"], "claude", machine["log"], scope=False)

    assert main(["install", "claude", "--scope", "project"]) == 0

    assert "skipped" in capsys.readouterr().out
    assert not machine["log"].exists()
    assert not (machine["home"] / ".claude" / "settings.json").exists()


def test_dry_run_changes_nothing(machine, capsys):
    """
    Scenario: Previewing what an install would do
      Given a machine with no harness CLI
      When the operator runs `the-loop install claude --dry-run`
      Then the plan is printed with the file it would write
      And no settings file exists afterwards
    """
    assert main(["install", "claude", "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert "dry run" in out and "planned" in out
    assert not (machine["home"] / ".claude").exists()


def test_a_failing_harness_command_exits_non_zero(machine, capsys):
    """
    Scenario: The harness refuses the install
      Given `claude` on PATH whose `plugin install` exits 3
      When the operator runs `the-loop install claude`
      Then the step is reported failed with the exit code
      And the process exits non-zero
    """
    fake_harness(machine["bin"], "claude", machine["log"], exit_code=3)

    assert main(["install", "claude"]) == 1
    assert "failed" in capsys.readouterr().out


def test_an_invalid_marketplace_never_reaches_the_machine(machine, capsys):
    """
    Scenario: A marketplace source that is not owner/repo
      Given `claude` on PATH exposing a plugin surface
      When the operator passes `--from "owner/repo; rm -rf /"`
      Then the run is refused before any command is executed
      And nothing is written to the settings file
    """
    fake_harness(machine["bin"], "claude", machine["log"])

    assert main(["install", "claude", "--from", "owner/repo; rm -rf /"]) == 2

    assert not machine["log"].exists()
    assert not (machine["home"] / ".claude" / "settings.json").exists()


def test_json_format_reports_every_step(machine, capsys):
    """
    Scenario: A setup script wants machine-readable results
      Given a machine with no harness CLI
      When the operator runs `the-loop install claude --format json`
      Then each step is emitted with its component, outcome and target
    """
    assert main(["install", "claude", "--format", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert [entry["component"] for entry in payload] == ["claude"]
    assert payload[0]["outcome"] == "applied"
    assert payload[0]["command"].endswith("settings.json")


def test_default_components_are_the_cli_plus_detected_harnesses(machine, capsys):
    """
    Scenario: An operator names no component
      Given `claude` on PATH
      When the operator runs `the-loop install --dry-run`
      Then the plan covers the CLI and Claude Code, and nothing runs
    """
    fake_harness(machine["bin"], "claude", machine["log"])

    assert main(["install", "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert "components: cli, claude" in out
    assert not machine["log"].exists()
