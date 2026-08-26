"""Service lifecycle: start is idempotent, stop waits (issue-161, T7)."""

import json
import os
import pathlib
import socket
import subprocess
import sys

import pytest

from the_loop.api.config import service_pidfile
from the_loop.migrations import CURRENT_CONFIG_VERSION
from the_loop.runlock import RunLock


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def service_env(tmp_path, monkeypatch):
    port = _free_port()
    config_path = tmp_path / "cli-config.yaml"
    config_path.write_text(
        f"version: '{CURRENT_CONFIG_VERSION}'\n"
        f"state:\n  root: {tmp_path / '.the-loop'}\n"
        f"service:\n  port: {port}\n"
    )
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(config_path))
    config = {
        "state": {"root": str(tmp_path / ".the-loop")},
        "service": {"port": port},
    }
    yield config
    lock = RunLock(service_pidfile(config), name="service")
    if lock.is_held():
        os.kill(lock.holder(), 15)
        lock.wait_until_free(10)


def _run_cli(*argv):
    return subprocess.run(
        [sys.executable, "-m", "the_loop", *argv],
        capture_output=True,
        text=True,
        timeout=60,
        env=os.environ.copy(),
    )


def test_start_stop_and_idempotency(service_env):
    """
    Feature: control-plane service lifecycle
      Scenario: an operator starts, re-starts and stops the service
        Given no service is running
        When `the-loop start` runs twice and then `the-loop stop`
        Then the first start boots a healthy service,
             the second reports it is already running without a second boot,
             and stop waits until the process has actually exited

    Requirement: docs/specs/issue-161/requirements.md R4.1, R4.3; issue-228 R1.3
    """
    from the_loop import client

    first = _run_cli("start")
    assert first.returncode == 0, first.stderr
    assert "started" in first.stdout
    assert client.healthy(service_env)

    second = _run_cli("start")
    assert second.returncode == 0
    assert "already-running" in second.stdout

    status = _run_cli("status")
    assert "running" in status.stdout

    stop = _run_cli("stop")
    assert stop.returncode == 0, stop.stderr
    assert "stopped" in stop.stdout
    assert not RunLock(service_pidfile(service_env), name="service").is_held()

    again = _run_cli("stop")
    assert again.returncode == 0
    assert "not-running" in again.stdout


def test_cli_routes_through_the_service(service_env):
    """
    Feature: the CLI is a client of the service
      Scenario: a client performs an authenticated read over HTTP
        Given a started service
        When the stdlib client lists work items and sessions
        Then the service answers with the durable stores' contents

    Requirement: docs/specs/issue-161/requirements.md R2.2, R3.1
    """
    from the_loop import client

    assert _run_cli("start").returncode == 0
    connection = client.connect(service_env)
    assert connection.get("/work-items") == []
    assert connection.get("/sessions") == []
    assert _run_cli("stop").returncode == 0


@pytest.mark.routed
def test_every_routed_command_works_over_the_transport(service_env, tmp_path):
    """
    Feature: the service is the CLI's only execution path
      Scenario: an operator runs the routed commands against a live service
        Given a started service and no THE_LOOP_SERVICE_LOCAL escape
        When sessions register/list/close, scenarios, instructions, critic list
             and graph show/status are run as real CLI invocations
        Then each one answers from the service, with the exit code and the
             wording its local path produced

    Requirement: docs/specs/issue-161/requirements.md R2.1, R2.2, R2.3
    """
    ref = "github:octo/repo#15"
    assert _run_cli("start").returncode == 0

    registered = _run_cli(
        "sessions",
        "register",
        "--work-item",
        ref,
        "--harness",
        "claude",
        "--harness-session-id",
        "sess-1",
        "--cwd",
        str(tmp_path),
    )
    assert registered.returncode == 0, registered.stderr
    assert f"registered {ref}" in registered.stdout

    listed = _run_cli("sessions", "list")
    assert listed.returncode == 0
    assert ref in listed.stdout and "claude" in listed.stdout

    # A second registration is the caller's mistake — a 400 the CLI renders as
    # its own exit 2, not an opaque transport error.
    duplicate = _run_cli(
        "sessions",
        "register",
        "--work-item",
        ref,
        "--harness",
        "claude",
        "--harness-session-id",
        "sess-2",
        "--cwd",
        str(tmp_path),
    )
    assert duplicate.returncode == 2
    assert "force" in duplicate.stderr

    closed = _run_cli("sessions", "close", "--work-item", ref)
    assert closed.returncode == 0, closed.stderr
    assert f"closed session for {ref}" in closed.stdout

    repo_root = str(pathlib.Path(__file__).resolve().parents[2])
    scenarios = _run_cli("scenarios", "--root", repo_root, "--format", "json")
    assert scenarios.returncode == 0, scenarios.stderr
    assert json.loads(scenarios.stdout)

    instructions = _run_cli("instructions", "--root", repo_root, "--format", "json")
    assert instructions.returncode == 0, instructions.stderr
    assert isinstance(json.loads(instructions.stdout), list)

    critics = _run_cli("critic", "list", "--root", repo_root, "--format", "json")
    assert critics.returncode == 0, critics.stderr

    show = _run_cli("graph", "--repo", repo_root, "show", "--format", "json")
    assert show.returncode == 0, show.stderr
    assert json.loads(show.stdout)["nodes"]

    # `check` already routed; assert it still does now that it sources its spec
    # root from the service rather than a locally built runtime.
    check = _run_cli("check", "issue-161", "--repo", repo_root, "--format", "json")
    assert check.returncode in (0, 1), check.stderr
    assert json.loads(check.stdout)["workItem"] == "issue-161"

    assert _run_cli("stop").returncode == 0


@pytest.mark.routed
def test_a_routed_command_fails_closed_when_no_service_can_start(
    service_env, tmp_path, monkeypatch
):
    """
    Feature: the service is the CLI's only execution path
      Scenario: no service is reachable and auto-start is off
        Given service.autoStart is false and nothing is listening
        When `the-loop sessions list` runs
        Then it names the lifecycle command and exits non-zero — it never
             quietly executes the core logic in-process

    Requirement: docs/specs/issue-161/requirements.md R2.3
    """
    config_path = tmp_path / "no-autostart.yaml"
    config_path.write_text(
        f"version: '{CURRENT_CONFIG_VERSION}'\n"
        f"state:\n  root: {tmp_path / '.the-loop'}\n"
        f"service:\n  port: {_free_port()}\n  autoStart: false\n"
    )
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(config_path))
    result = _run_cli("sessions", "list")
    assert result.returncode == 2
    assert "the-loop start" in result.stderr
