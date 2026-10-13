"""A real tmux spawn keeps every secret out of `ps` and out of the pane (T4).

issue-482: the daemon held `env.file` and handed it to every pane as `-e NAME=value`.
issue-485: when that `tmux new-session` started the server, the server kept the token
in its own command line for days. This test spawns through a real tmux, on a private
server (``TMUX_TMPDIR``), from a process that holds a dummy token, and reads back
the server's command line and the pane's environment.

Spec: docs/specs/issue-482/testing-plan.md row T4.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from the_loop import envstate
from the_loop.harness import ClaudeCodeAdapter
from the_loop.runner import TmuxRunner

SECRET = "dummy-secret-value-482"
REF = "github:octo/repo#482"


def _tmux_ok() -> bool:
    if shutil.which("tmux") is None or not Path("/proc/self/environ").exists():
        return False
    out = subprocess.run(["tmux", "-V"], capture_output=True, text=True).stdout
    match = re.search(r"(\d+)\.(\d+)", out)
    return bool(match) and (int(match.group(1)), int(match.group(2))) >= (3, 2)


pytestmark = pytest.mark.skipif(
    not _tmux_ok(), reason="needs tmux 3.2+ and /proc (Linux) to read a pane back"
)


class _SleepAdapter(ClaudeCodeAdapter):
    """A harness stand-in: a shell that sleeps, so the pane stays up to be read."""

    default_binary = "sh"

    def interactive_argv(self, prompt, session_id):
        return ["-c", "sleep 30"]

    def interactive_resume_argv(self, prompt, session_id):
        return ["-c", "sleep 30"]

    def resolve_session_id(self, cwd, session_id):
        return session_id


@pytest.fixture
def private_tmux(tmp_path, monkeypatch):
    """A tmux server nobody else uses, started — like issue-485's — by the spawn."""
    sockets = tmp_path / "tmux"
    sockets.mkdir()
    monkeypatch.setenv("TMUX_TMPDIR", str(sockets))
    monkeypatch.delenv("TMUX", raising=False)
    yield
    subprocess.run(["tmux", "kill-server"], capture_output=True)


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8", "replace")


def test_issue_485_a_spawned_server_and_its_pane_hold_no_secret(
    tmp_path, monkeypatch, private_tmux
):
    """
    Feature: spawned sessions never receive a secret
      Scenario: the daemon holds the token, and no tmux server is running
        Given a process holding GH_TOKEN and an env file declaring JIRA_API_TOKEN
        When it spawns a session and that spawn starts the tmux server
        Then the server's command line carries neither value
        And the pane's environment holds neither name
        And the pane still carries THE_LOOP_WORK_ITEM

    Requirement: docs/specs/issue-482/requirements.md R1.1–R1.4, R2.1–R2.3
    """
    env_file = tmp_path / ".env"
    env_file.write_text(f"JIRA_API_TOKEN={SECRET}-jira\n")
    config = {"env": {"file": str(env_file)}}
    # The daemon loaded its env file at start: both are in its environment.
    monkeypatch.setenv("GH_TOKEN", SECRET)
    monkeypatch.setenv("JIRA_API_TOKEN", f"{SECRET}-jira")
    runner = TmuxRunner(
        instance="t4", env_provider=lambda: envstate.spawn_environment(lambda: config)
    )
    result = runner.spawn_in(
        "loop-github-octo-repo-482",
        _SleepAdapter(),
        "go",
        cwd=str(tmp_path),
        session_id="s1",
        work_item=REF,
    )
    assert result.ok, result.error

    server_pid = int(
        subprocess.run(
            [
                "tmux",
                "display-message",
                "-p",
                "-t",
                "loop-github-octo-repo-482",
                "#{pid}",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    pane_pid = 0
    for _ in range(50):
        listed = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-t",
                "loop-github-octo-repo-482",
                "-F",
                "#{pane_pid}",
            ],
            capture_output=True,
            text=True,
        ).stdout.split()
        if listed:
            pane_pid = int(listed[0])
            # `env -u` then `exec`: wait until the pane is the harness itself.
            if _read(Path(f"/proc/{pane_pid}/cmdline")).startswith("sh\0"):
                break
        time.sleep(0.1)
    assert pane_pid

    server_cmdline = _read(Path(f"/proc/{server_pid}/cmdline"))
    server_environ = _read(Path(f"/proc/{server_pid}/environ"))
    pane_environ = _read(Path(f"/proc/{pane_pid}/environ"))
    assert SECRET not in server_cmdline
    assert SECRET not in server_environ
    assert SECRET not in pane_environ
    names = {entry.split("=", 1)[0] for entry in pane_environ.split("\0") if entry}
    assert "GH_TOKEN" not in names and "JIRA_API_TOKEN" not in names
    assert f"THE_LOOP_WORK_ITEM={REF}" in pane_environ.split("\0")
