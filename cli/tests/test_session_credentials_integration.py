"""A real tmux spawn hands over an opted-in credential that no argv holds (T2).

issue-533: `env.sessionCredentials` lets an operator give a session a token. The value
reaches the pane through a 0600 file the pane reads and deletes; this test spawns
through a real tmux on a private server, started by the spawn itself (issue-485's
worst case), and reads back every place the value must not be.

Spec: docs/specs/issue-533/testing-plan.md row T2.
"""

from __future__ import annotations

import re
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

from the_loop import envstate
from the_loop.harness import ClaudeCodeAdapter
from the_loop.runner import TmuxRunner

VALUE = "session-credential-value-533"
ROTATED = "session-credential-rotated-533"
DAEMON = "daemon-own-token-value-533"
REF = "github:octo/repo#533"
TARGET = "loop-github-octo-repo-533"
# The harness stand-in, before or after `sh -c` execs its one command.
HARNESS = ("sh\0-c\0sleep 30\0", "sleep\x0030\0")


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
    sockets = tmp_path / "tmux"
    sockets.mkdir()
    monkeypatch.setenv("TMUX_TMPDIR", str(sockets))
    monkeypatch.delenv("TMUX", raising=False)
    yield
    subprocess.run(["tmux", "kill-server"], capture_output=True)


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8", "replace")


def _tmux(*args: str) -> str:
    return subprocess.run(
        ["tmux", *args], capture_output=True, text=True, check=True
    ).stdout


def _harness_pid(target: str) -> int:
    """The pane's pid once the loader has exec'd into the harness."""
    for _ in range(100):
        listed = _tmux("list-panes", "-t", target, "-F", "#{pane_pid}").split()
        if listed:
            pid = int(listed[0])
            try:
                if _read(Path(f"/proc/{pid}/cmdline")) in HARNESS:
                    return pid
            except OSError:
                pass
        time.sleep(0.05)
    raise AssertionError(f"{target}'s pane never became the harness")


def _environ(pid: int) -> dict:
    return dict(
        entry.split("=", 1)
        for entry in _read(Path(f"/proc/{pid}/environ")).split("\0")
        if "=" in entry
    )


def _config(tmp_path, value: str) -> dict:
    env_file = tmp_path / ".env"
    env_file.write_text(f"SESSION_GH_TOKEN={value}\n")
    return {
        "env": {
            "file": str(env_file),
            "sessionCredentials": [{"name": "GH_TOKEN", "from": "SESSION_GH_TOKEN"}],
        }
    }


def test_issue_533_a_spawned_session_inherits_a_credential_no_argv_holds(
    tmp_path, monkeypatch, private_tmux
):
    """
    Feature: opt-in session credentials, never on argv
      Scenario: a spawned session inherits an opted-in credential that no argv or tmux environment holds
        Given the daemon holds its own GH_TOKEN and an env file declaring SESSION_GH_TOKEN
        And env.sessionCredentials hands GH_TOKEN from SESSION_GH_TOKEN to sessions
        When it spawns a session and that spawn starts the tmux server
        Then the pane's environment holds GH_TOKEN with the session value
        And no process's argv holds the value, nor the server's environment
        And tmux's global environment does not hold it
        And the delivery file is gone once the harness runs

    Requirement: docs/specs/issue-533/requirements.md R3.1–R3.5
    """
    config = _config(tmp_path, VALUE)
    monkeypatch.setenv("GH_TOKEN", DAEMON)
    creds = tmp_path / "state" / "local" / "session-credentials"
    runner = TmuxRunner(
        instance="t2",
        env_provider=lambda: envstate.spawn_environment(lambda: config),
        credentials_dir=str(creds),
    )
    result = runner.spawn_in(
        TARGET, _SleepAdapter(), "go", cwd=str(tmp_path), session_id="s1", work_item=REF
    )
    assert result.ok, result.error
    pane = _harness_pid(TARGET)

    pane_env = _environ(pane)
    assert pane_env.get("GH_TOKEN") == VALUE
    assert "SESSION_GH_TOKEN" not in pane_env
    assert pane_env.get("THE_LOOP_WORK_ITEM") == REF

    server = int(_tmux("display-message", "-p", "-t", TARGET, "#{pid}").strip())
    assert VALUE not in _read(Path(f"/proc/{server}/cmdline"))
    server_environ = _read(Path(f"/proc/{server}/environ"))
    assert VALUE not in server_environ and DAEMON not in server_environ
    assert VALUE not in _tmux("show-environment", "-g")
    assert VALUE not in _tmux("show-environment", "-t", TARGET)

    args = subprocess.run(
        ["ps", "-eo", "args"], capture_output=True, text=True, check=True
    ).stdout
    assert VALUE not in args

    assert stat.S_IMODE(creds.stat().st_mode) == 0o700
    assert list(creds.iterdir()) == []


def test_issue_533_a_second_session_does_not_inherit_it(
    tmp_path, monkeypatch, private_tmux
):
    """
    Feature: opt-in session credentials, never on argv
      Scenario: a second session on the same server does not inherit the credential
        Given a session that inherited GH_TOKEN started the tmux server
        When an unrelated tmux session (the web-terminal hub) starts on that server
        Then its shell holds neither the value nor the name

    Requirement: docs/specs/issue-533/requirements.md R3.6
    """
    config = _config(tmp_path, VALUE)
    runner = TmuxRunner(
        env_provider=lambda: envstate.spawn_environment(lambda: config),
        credentials_dir=str(tmp_path / "creds"),
    )
    assert runner.spawn_in(
        TARGET, _SleepAdapter(), "go", cwd=str(tmp_path), session_id="s1", work_item=REF
    ).ok
    _harness_pid(TARGET)
    _tmux("new-session", "-d", "-s", "the-loop-hub", "sleep 30")
    hub = int(_tmux("list-panes", "-t", "the-loop-hub", "-F", "#{pane_pid}").split()[0])
    hub_env = _environ(hub)
    assert "GH_TOKEN" not in hub_env
    assert VALUE not in _read(Path(f"/proc/{hub}/environ"))


def test_issue_533_rotating_the_source_marks_the_session_stale(
    tmp_path, monkeypatch, private_tmux
):
    """
    Feature: opt-in session credentials, never on argv
      Scenario: rotating the source value marks the session stale
        Given a running session that inherited GH_TOKEN
        When the operator rotates SESSION_GH_TOKEN in the env file
        Then the session reads stale on GH_TOKEN, shown by fingerprint only
        And a respawn delivers the rotated value and reads fresh

    Requirement: docs/specs/issue-533/requirements.md R4.1, R4.2
    """
    config = _config(tmp_path, VALUE)
    config_path = tmp_path / "cli-config.yaml"
    runner = TmuxRunner(
        env_provider=lambda: envstate.spawn_environment(lambda: config),
        credentials_dir=str(tmp_path / "creds"),
    )
    assert runner.spawn_in(
        TARGET, _SleepAdapter(), "go", cwd=str(tmp_path), session_id="s1", work_item=REF
    ).ok
    pane = _harness_pid(TARGET)
    wanted = envstate.session_environment(config, config_path).for_work_item(REF)
    assert envstate.environ_matches_declared(wanted, pane) == ("fresh", ())

    (tmp_path / ".env").write_text(f"SESSION_GH_TOKEN={ROTATED}\n")
    wanted = envstate.session_environment(config, config_path).for_work_item(REF)
    assert envstate.environ_matches_declared(wanted, pane) == ("stale", ("GH_TOKEN",))
    assert envstate.held_credentials(wanted, _environ(pane)) == {
        "GH_TOKEN": envstate.fingerprint(VALUE)
    }

    assert runner.respawn_in(
        TARGET, _SleepAdapter(), "go", cwd=str(tmp_path), session_id="s1", work_item=REF
    ).ok
    for _ in range(100):
        pane = _harness_pid(TARGET)
        if _environ(pane).get("GH_TOKEN") == ROTATED:
            break
        time.sleep(0.05)
    assert envstate.environ_matches_declared(wanted, pane) == ("fresh", ())
