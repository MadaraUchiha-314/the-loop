"""Unit tests for the SessionStart hook script (hooks/session-start.sh).

The hook has two jobs (issue #38): auto-upgrade the installed plugin's git
checkout to origin so every new session runs the latest the-loop, and surface
the project's the-loop config reminder. It must never block or fail a session.

Run with: pytest (from the cli/ directory).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "hooks" / "session-start.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("sh") is None,
    reason="requires git and sh",
)


def _git(cwd: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()


def _run(plugin_root: Path | None, cwd: Path, **extra_env: str):
    env = {**os.environ}
    env.pop("THE_LOOP_AUTO_UPGRADE", None)
    if plugin_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    else:
        env.pop("CLAUDE_PLUGIN_ROOT", None)
    env.update(extra_env)
    return subprocess.run(
        ["sh", str(SCRIPT)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def plugin_and_upstream(tmp_path: Path):
    """An upstream repo one commit ahead of a plugin clone tracking `main`."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-q", "-b", "main")
    (upstream / "f.txt").write_text("v1\n")
    _git(upstream, "add", "f.txt")
    _git(upstream, "commit", "-q", "-m", "v1")

    plugin = tmp_path / "plugin"
    _git(tmp_path, "clone", "-q", str(upstream), str(plugin))

    # Advance upstream so the plugin is now behind.
    (upstream / "f.txt").write_text("v2\n")
    _git(upstream, "commit", "-qam", "v2")
    return plugin, upstream


def test_auto_upgrade_fast_forwards_plugin(plugin_and_upstream, tmp_path):
    plugin, _ = plugin_and_upstream
    result = _run(plugin, cwd=tmp_path)
    assert result.returncode == 0
    assert (plugin / "f.txt").read_text() == "v2\n"
    assert "auto-upgraded plugin" in result.stdout


def test_second_run_is_silent_when_up_to_date(plugin_and_upstream, tmp_path):
    plugin, _ = plugin_and_upstream
    _run(plugin, cwd=tmp_path)  # first run pulls v2
    result = _run(plugin, cwd=tmp_path)  # already current
    assert result.returncode == 0
    assert "auto-upgraded" not in result.stdout


def test_opt_out_env_skips_upgrade(plugin_and_upstream, tmp_path):
    plugin, _ = plugin_and_upstream
    result = _run(plugin, cwd=tmp_path, THE_LOOP_AUTO_UPGRADE="0")
    assert result.returncode == 0
    assert (plugin / "f.txt").read_text() == "v1\n"  # untouched
    assert "auto-upgraded" not in result.stdout


def test_dirty_checkout_is_left_alone(plugin_and_upstream, tmp_path):
    plugin, _ = plugin_and_upstream
    (plugin / "f.txt").write_text("local edit\n")
    result = _run(plugin, cwd=tmp_path)
    assert result.returncode == 0
    assert (plugin / "f.txt").read_text() == "local edit\n"
    assert "auto-upgraded" not in result.stdout


def test_config_reminder_emitted_when_initialized(tmp_path):
    project = tmp_path / "project"
    (project / ".the-loop").mkdir(parents=True)
    (project / ".the-loop" / "config.yaml").write_text("version: '0.1.0'\n")
    result = _run(plugin_root=None, cwd=project)
    assert result.returncode == 0
    assert "the-loop is initialized in this repo" in result.stdout


def test_no_plugin_root_and_no_config_is_silent_and_succeeds(tmp_path):
    result = _run(plugin_root=None, cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_missing_plugin_checkout_does_not_fail(tmp_path):
    # CLAUDE_PLUGIN_ROOT points at a non-git directory: upgrade is skipped cleanly.
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    result = _run(not_a_repo, cwd=tmp_path)
    assert result.returncode == 0
    assert "auto-upgraded" not in result.stdout
