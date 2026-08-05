"""Service lifecycle: start is idempotent, stop waits (issue-161, T7)."""

import os
import socket
import subprocess
import sys

import pytest

from the_loop.api.config import service_pidfile, token_path
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
        "version: '0.4.0'\n"
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
        When `the-loop service start` runs twice and then `service stop`
        Then the first start boots a healthy service and mints a 0600 token,
             the second reports it is already running without a second boot,
             and stop waits until the process has actually exited

    Requirement: docs/specs/issue-161/requirements.md R4.1, R4.3
    """
    from the_loop import client

    first = _run_cli("service", "start")
    assert first.returncode == 0, first.stderr
    assert "service started" in first.stdout
    assert client.healthy(service_env)

    token_file = token_path(service_env)
    assert token_file.is_file()
    assert oct(token_file.stat().st_mode & 0o777) == "0o600"

    second = _run_cli("service", "start")
    assert second.returncode == 0
    assert "already running" in second.stdout

    status = _run_cli("service", "status")
    assert "running" in status.stdout

    stop = _run_cli("service", "stop")
    assert stop.returncode == 0, stop.stderr
    assert "stopped" in stop.stdout
    assert not RunLock(service_pidfile(service_env), name="service").is_held()

    again = _run_cli("service", "stop")
    assert again.returncode == 0
    assert "not running" in again.stdout


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

    assert _run_cli("service", "start").returncode == 0
    connection = client.connect(service_env)
    assert connection.get("/work-items") == []
    assert connection.get("/sessions") == []
    assert _run_cli("service", "stop").returncode == 0
