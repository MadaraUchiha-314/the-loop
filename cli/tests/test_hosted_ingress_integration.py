"""Single-process mode against real processes (issue-231).

`service.hostIngresses` (the default) makes `the-loop start` boot ONE process:
uvicorn serving /api/v1 (+ /mcp), with the poller and the webhook receiver as
hosted threads under the same lifespan. The claims worth a real-process test:

- one pid: the poller's and receiver's pidfile locks are held by the service's
  own pid, and every surface (`start`'s rows, `status --format json`) says so;
- the hosted receiver actually answers on its own port;
- `the-loop stop` stops the one process and all three locks are released.

Same conventions as test_poll_daemon_integration: temp state root, a stub `gh`
on PATH so a poll cycle completes with no network, everything killed in
``finally``.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from the_loop.runlock import RunLock

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="lifecycle tests need POSIX signals"
)

FAKE_GH = """#!/bin/sh
case "$1" in
  --version) echo "gh version 2.60.0 (fake)" ;;
  auth) exit 0 ;;
  *) echo "[]" ;;
esac
exit 0
"""

CLI = [
    sys.executable,
    "-c",
    "import sys; from the_loop.cli import main; sys.exit(main())",
]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def env(tmp_path):
    root = tmp_path / ".the-loop"
    root.mkdir()
    service_port = _free_port()
    receiver_port = _free_port()
    (root / "cli-config.yaml").write_text(
        f"""
service:
  port: {service_port}
webhooks:
  ghWebhook:
    enabled: true
    port: {receiver_port}
routing:
  enabled: false
  authorizedUsers: ["octocat"]
polling:
  enabled: true
  intervalSeconds: 1
  sources:
    - provider: github
      repos: ["octo/repo"]
"""
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)

    environ = dict(os.environ)
    environ["PATH"] = f"{bin_dir}{os.pathsep}{environ.get('PATH', '')}"
    environ["THE_LOOP_CLI_CONFIG"] = str(root / "cli-config.yaml")
    environ["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    environ.pop("THE_LOOP_SERVICE_LOCAL", None)
    return {
        "cwd": tmp_path,
        "root": root,
        "environ": environ,
        "service_port": service_port,
        "receiver_port": receiver_port,
        "service_pidfile": root / "local" / "service.pid",
        "poll_pidfile": root / "poll.pid",
        "receiver_pidfile": root / "gh-webhook.pid",
    }


def _cli(env, *argv, timeout=120):
    return subprocess.run(
        [*CLI, *argv],
        cwd=str(env["cwd"]),
        env=env["environ"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _holder(pidfile) -> int:
    return RunLock(pidfile).holder() if Path(pidfile).is_file() else 0


def _kill(pid: int) -> None:
    if pid <= 0:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(100):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def test_start_hosts_everything_in_one_process_and_stop_ends_it(env):
    """
    Feature: single-process mode (service.hostIngresses)
    Scenario: start → one pid; status says hosted; stop ends everything
        Given the service, the receiver and the poller all enabled with
        hostIngresses at its default
        When `the-loop start` runs
        Then the poller and receiver rows read `hosted`, all three pidfile
        locks are held by the service's pid, the hosted receiver answers
        /health on its own port — and `the-loop stop` releases all of it
    Requirement: github issue #231
    """
    result = _cli(env, "start")
    service_pid = _holder(env["service_pidfile"])
    try:
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.count("hosted") >= 2, result.stdout
        assert service_pid > 0

        # One pid for all three: the hosted locks are the service's.
        assert _holder(env["poll_pidfile"]) == service_pid
        assert _holder(env["receiver_pidfile"]) == service_pid
        assert RunLock(env["poll_pidfile"], name="poller").is_held()
        assert RunLock(env["receiver_pidfile"], name="gh-webhook").is_held()

        # The hosted receiver serves on its own port from inside that pid.
        with urllib.request.urlopen(
            f"http://127.0.0.1:{env['receiver_port']}/health", timeout=5
        ) as response:
            assert response.status == 200

        status = _cli(env, "status", "--format", "json")
        assert status.returncode == 0, status.stdout
        report = json.loads(status.stdout)
        rows = {row["service"]: row for row in report["services"]}
        assert rows["service"]["pid"] == service_pid
        assert rows["poller"]["hosted"] is True
        assert rows["gh-webhook"]["hosted"] is True
        assert report["ok"] is True

        stop = _cli(env, "stop")
        assert stop.returncode == 0, stop.stdout + stop.stderr
        assert "hosted in the service" in stop.stdout
        assert not RunLock(env["service_pidfile"], name="service").is_held()
        assert not RunLock(env["poll_pidfile"], name="poller").is_held()
        assert not RunLock(env["receiver_pidfile"], name="gh-webhook").is_held()
    finally:
        _kill(service_pid)


def test_a_standalone_daemon_is_not_fought_over(env):
    """
    Feature: single-process mode (service.hostIngresses)
    Scenario: the poller's lock is already held by a standalone daemon
        Given a running standalone poller
        When `the-loop start` boots the hosting service
        Then the service comes up without hosting the poller (skip, not a
        fight over the lock) and start reports the poller as already-running
    Requirement: github issue #231 (single-instance guarantee holds across modes)
    """
    holder = RunLock(env["poll_pidfile"], name="poller")
    assert holder.acquire()  # this test process stands in for a standalone poller
    service_pid = 0
    try:
        result = _cli(env, "start")
        service_pid = _holder(env["service_pidfile"])
        assert service_pid > 0 and service_pid != os.getpid()
        row = next(
            line for line in result.stdout.splitlines() if line.startswith("poller")
        )
        assert "already-running" in row
        assert "standalone" in row
        # The standalone holder keeps its lock; the service did not steal it.
        assert _holder(env["poll_pidfile"]) == os.getpid()
    finally:
        holder.release()
        _kill(service_pid)
