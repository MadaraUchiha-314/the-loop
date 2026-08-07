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


# -- Cursor (issue-157) --------------------------------------------------------
#
# Feature: Installing the-loop's Cursor plugin from the same command
# Requirement: docs/specs/issue-157/requirements.md


def test_a_detected_cursor_joins_the_default_set_and_drives_its_own_cli(
    machine, capsys
):
    """
    Scenario: A machine with both harnesses, and a Cursor that manages plugins
      Given `claude` and `cursor-agent` on PATH, both exposing a plugin surface
      When the operator runs `the-loop install` naming no component
      Then the plan covers the CLI and both harnesses
      And running it drives cursor-agent's own marketplace-add and plugin-install
      And no clone is made under Cursor's local plugins directory
    """
    fake_harness(machine["bin"], "claude", machine["log"])
    cursor_log = machine["log"].parent / "cursor.log"
    fake_harness(machine["bin"], "cursor-agent", cursor_log)

    # Naming no component selects `cli` too, and the CLI step is a real package
    # install — so the default set is asserted under --dry-run, and the harness steps
    # are then executed by naming them.
    assert main(["install", "--dry-run"]) == 0
    assert "components: cli, claude, cursor" in capsys.readouterr().out
    assert not cursor_log.exists()

    assert main(["install", "claude", "cursor", "--from", "acme/loop"]) == 0

    assert cursor_log.read_text(encoding="utf-8").splitlines() == [
        "plugin marketplace add acme/loop --scope user",
        f"plugin install {PLUGIN_KEY} --scope user",
    ]
    assert not (machine["home"] / ".cursor").exists()


def test_without_a_cursor_plugin_cli_the_documented_clone_is_planned(machine, capsys):
    """
    Scenario: A Cursor build with no CLI install command
      Given no `cursor-agent` on PATH and a `git` that records what it was asked to do
      When the operator runs `the-loop install cursor --format json`
      Then the single step is a git clone of the resolved marketplace into
           ~/.cursor/plugins/local/the-loop
      And re-running it reports `already` without running git again
    """
    # The fake PATH holds only our stubs, so the stub restores a real one for `mkdir`.
    _script(machine["bin"] / "git", 'PATH=/usr/bin:/bin mkdir -p "$4/.git"\n')
    directory = machine["home"] / ".cursor" / "plugins" / "local" / "the-loop"

    assert main(["install", "cursor", "--from", "acme/loop", "--format", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert [entry["component"] for entry in payload] == ["cursor"]
    assert payload[0]["outcome"] == "applied"
    assert payload[0]["command"] == (
        f"{machine['bin']}/git clone -- https://github.com/acme/loop.git {directory}"
    )
    assert (directory / ".git").is_dir()

    assert main(["install", "cursor", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["outcome"] == "already"


def test_a_cursor_destination_that_is_not_a_checkout_is_left_alone(machine, capsys):
    """
    Scenario: Something else already occupies Cursor's local plugin directory
      Given ~/.cursor/plugins/local/the-loop holding files this command did not create
      When the operator runs `the-loop install cursor`
      Then the component is reported skipped, naming the path
      And the directory's contents are unchanged
    """
    _script(machine["bin"] / "git", f'echo "git ran" >> "{machine["log"]}"\n')
    directory = machine["home"] / ".cursor" / "plugins" / "local" / "the-loop"
    directory.mkdir(parents=True)
    occupant = directory / "notes.txt"
    occupant.write_text("mine\n", encoding="utf-8")

    assert main(["install", "cursor"]) == 0

    assert "skipped" in capsys.readouterr().out
    assert not machine["log"].exists()
    assert occupant.read_text(encoding="utf-8") == "mine\n"
    assert list(directory.iterdir()) == [occupant]
