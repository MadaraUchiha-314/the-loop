"""A detached poller, against the real process table (issue-191, T6/T7).

Everything else about this work item is ordinary unit-testable code. Detaching is
not: mocking ``os.fork`` would prove only that we called it, and the properties
that matter — reparenting to init, owning a session, surviving the teardown of
the process group that started it — are statements about the running system.

So these tests spawn ``the-loop poll start --daemon`` as a real subprocess against
a temporary ``state.root``, and then interrogate the kernel: ``/proc`` where it is
available, ``ps`` where it is not. Every test kills what it spawned in a
``finally``; nothing here reaches the network (the ``gh`` on ``PATH`` is a stub
that lists no work items) and nothing spawns a session.

Spec: docs/specs/issue-191/design.md; testing plan rows T6, T7.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from the_loop.runlock import RunLock

pytestmark = pytest.mark.skipif(
    not hasattr(os, "fork"), reason="daemonizing needs POSIX fork"
)

CONFIG = """
routing:
  enabled: false
  authorizedUsers: ["octocat"]
polling:
  intervalSeconds: 1
  sources:
    - provider: github
      repos: ["octo/repo"]
"""

#: A `gh` that satisfies the dependency check and lists nothing, so a cycle runs
#: to completion with no network and no spawn.
FAKE_GH = """#!/bin/sh
case "$1" in
  --version) echo "gh version 2.60.0 (fake)" ;;
  auth) exit 0 ;;
  *) echo "[]" ;;
esac
exit 0
"""


@pytest.fixture
def env(tmp_path):
    """A temp working directory with a CLI config and a stub `gh` on PATH."""
    root = tmp_path / ".the-loop"
    root.mkdir()
    (root / "cli-config.yaml").write_text(CONFIG)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)

    environ = dict(os.environ)
    environ["PATH"] = f"{bin_dir}{os.pathsep}{environ.get('PATH', '')}"
    environ["THE_LOOP_CLI_CONFIG"] = str(root / "cli-config.yaml")
    environ["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    return {
        "cwd": tmp_path,
        "root": root,
        "environ": environ,
        "pidfile": root / "poll.pid",
        "logfile": root / "logs" / "poller.out",
        "status": root / "poll-status.json",
        # The paths default relative to the working directory, and that is what
        # the command prints back — so that is what the assertions look for.
        "logfile_arg": ".the-loop/logs/poller.out",
    }


#: How the tests invoke the CLI. Not the console script: it is not guaranteed to
#: be on PATH in a bare checkout, and the point here is the process boundary, not
#: the packaging.
CLI = [
    sys.executable,
    "-c",
    "import sys; from the_loop.cli import main; sys.exit(main())",
]


def _start(env, *extra, **popen_kwargs):
    """Run `poll start` to completion in the *starter* process, returning it."""
    return subprocess.run(
        [*CLI, "poll", "start", *extra],
        cwd=str(env["cwd"]),
        env=env["environ"],
        capture_output=True,
        text=True,
        timeout=90,
        **popen_kwargs,
    )


def _daemon_pid(env) -> int:
    return RunLock(env["pidfile"], name="poller").holder()


def _kill(pid: int) -> None:
    if pid <= 0:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(100):
        if not _alive(pid):
            return
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _stat(pid: int) -> dict:
    """``{ppid, sid, pgid}`` for ``pid``, from /proc or ps."""
    proc_status = Path(f"/proc/{pid}/stat")
    if proc_status.is_file():
        # The comm field can contain spaces and parentheses; everything after the
        # final ')' is positional. Fields (1-indexed from there): state, ppid,
        # pgrp, session.
        fields = proc_status.read_text().rsplit(")", 1)[1].split()
        return {"ppid": int(fields[1]), "pgid": int(fields[2]), "sid": int(fields[3])}
    out = subprocess.run(
        ["ps", "-o", "ppid=,pgid=,sess=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return {"ppid": int(out[0]), "pgid": int(out[1]), "sid": int(out[2])}


def _wait_for(predicate, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


# -- the detach itself ----------------------------------------------------------


def test_a_daemonized_poller_owns_its_session_pidfile_and_log(env):
    """
    Feature: `poll start --daemon` runs as a proper daemon
    Scenario: A daemonized poller owns its pidfile and its logfile
        Given `poll start --daemon` is run in a temporary state root
        When the starting process returns
        Then it reports a pid that is not its own child, that pid holds the
        pidfile's lock, the daemon is its own session leader's child reparented
        away from the starter, and the logfile is receiving its output
    Requirement: github issue #191 (R1.1, R2.1, R3.1, R3.5)
    """
    result = _start(env, "--daemon")
    pid = _daemon_pid(env)
    try:
        assert result.returncode == 0, result.stderr
        assert f"poller started (pid {pid})" in result.stdout
        assert env["logfile_arg"] in result.stdout

        # The lock, not the file, is what proves it is running.
        assert RunLock(env["pidfile"], name="poller").is_held()
        assert pid > 0 and _alive(pid)

        stats = _stat(pid)
        assert stats["ppid"] != os.getpid(), "not a child of the test process"
        assert stats["sid"] == stats["pgid"] != os.getpgid(0), "its own session"

        assert _wait_for(
            lambda: env["logfile"].is_file() and env["logfile"].stat().st_size
        )
        assert "poll:" in env["logfile"].read_text()
    finally:
        _kill(pid)


def test_a_daemonized_poller_outlives_the_shell_that_started_it(env):
    """
    Feature: `poll start --daemon` runs as a proper daemon
    Scenario: A daemonized poller outlives the shell that started it
        Given a poller started from a process in its own process group
        When that whole process group is torn down with SIGKILL
        Then the poller is still running and still holds its lock
    Requirement: github issue #191 (R1.2)
    """
    # A starter in its own process group, so killing the group cannot reach the
    # test runner — this is the exact teardown that lost us a poller.
    starter = subprocess.Popen(
        [*CLI, "poll", "start", "--daemon"],
        cwd=str(env["cwd"]),
        env=env["environ"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    starter.communicate(timeout=90)
    # `start_new_session=True` makes the starter its own session and group leader,
    # so its pid IS the process-group id we are about to tear down.
    starter_group = starter.pid
    pid = _daemon_pid(env)
    try:
        assert pid > 0 and _alive(pid)
        stats = _stat(pid)
        assert stats["pgid"] != starter_group, "the daemon left the starter's group"
        assert stats["sid"] != starter_group, "…and the starter's session"

        try:
            os.killpg(starter_group, signal.SIGKILL)
        except ProcessLookupError:
            pass  # the group is already empty — which is the point being made
        time.sleep(0.5)

        assert _alive(pid), "the poller died with the group that started it"
        assert RunLock(env["pidfile"], name="poller").is_held()
    finally:
        _kill(pid)


def test_the_starter_leaves_no_zombie_behind(env):
    """
    Feature: `poll start --daemon` runs as a proper daemon
    Scenario: The intermediate child is reaped by the process that forked it
        Given the double-fork leaves an intermediate child that exits at once
        When the starting process returns
        Then it has reaped that child rather than leaving a zombie
    Requirement: github issue #191 (R1.1)
    """
    result = _start(env, "--daemon")
    pid = _daemon_pid(env)
    try:
        assert result.returncode == 0
        # The daemon is reparented away from the starter, and the starter has
        # exited — so nothing it forked can still be a child of anything but init.
        assert _stat(pid)["ppid"] != 0
    finally:
        _kill(pid)


# -- refusals and failures ------------------------------------------------------


def test_a_daemonized_start_refuses_when_a_poller_already_holds_the_lock(env):
    """
    Feature: the pidfile tells the truth
    Scenario: A daemonized start refuses when a poller already holds the lock
        Given a poller is already running against this state root
        When a second `poll start --daemon` is invoked
        Then it exits non-zero naming the holding pid, and the first poller is
        untouched
    Requirement: github issue #191 (R3.3); T7 abuse case
    """
    first = _start(env, "--daemon")
    pid = _daemon_pid(env)
    try:
        assert first.returncode == 0
        second = _start(env, "--daemon")

        assert second.returncode == 1
        assert f"another poller is already running (pid {pid}" in second.stderr
        assert _alive(pid), "the refusal must not disturb the running poller"
    finally:
        _kill(pid)


def test_a_daemonized_start_reports_a_startup_failure_to_its_caller(env):
    """
    Feature: `poll start --daemon` runs as a proper daemon
    Scenario: A daemonized start reports a startup failure to its caller
        Given a config whose polling sources are empty, so the poller exits at
        startup
        When `poll start --daemon` is invoked
        Then the starting process exits non-zero, points at the logfile, and no
        lock is left held
    Requirement: github issue #191 (R3.4)
    """
    (env["root"] / "cli-config.yaml").write_text(
        "routing:\n  enabled: false\npolling:\n  intervalSeconds: 1\n  sources: []\n"
    )
    result = _start(env, "--daemon")

    assert result.returncode == 1
    assert "the poller did not come up" in result.stderr
    assert env["logfile_arg"] in result.stderr
    assert not RunLock(env["pidfile"], name="poller").is_held()
    assert "no polling sources configured" in env["logfile"].read_text()


def test_a_stale_pidfile_is_removed_by_the_next_daemonized_start(env):
    """
    Feature: the pidfile tells the truth
    Scenario: A stale pidfile is removed by the next start
        Given a pidfile naming a pid no poller holds a lock for
        When `poll start --daemon` runs
        Then the stale pid is gone and the pidfile names the new daemon
    Requirement: github issue #191 (R3.2); T7 abuse case
    """
    env["pidfile"].write_text("999999\n")
    result = _start(env, "--daemon")
    pid = _daemon_pid(env)
    try:
        assert result.returncode == 0
        assert pid != 999999
        assert "removed a stale pidfile" in env["logfile"].read_text()
    finally:
        _kill(pid)


# -- status against a real daemon -----------------------------------------------


def test_status_reports_a_running_poller_its_pid_and_its_last_cycle(env):
    """
    Feature: `poll status` answers "is the poller actually running?"
    Scenario: poll status reports a running poller, its pid and its last cycle
        Given a daemonized poller that has completed at least one cycle
        When `poll status --format json` runs
        Then it exits 0 and reports running, that pid, and the cycle's counters —
        and after the poller stops it exits 1 while still reporting the cycle
    Requirement: github issue #191 (R4.1, R4.2, R4.3, R4.5)
    """
    result = _start(env, "--daemon")
    pid = _daemon_pid(env)
    try:
        assert result.returncode == 0
        assert _wait_for(
            lambda: (
                (beat := _read_json(env["status"])) is not None
                and beat.get("lastCycleAt")
            )
        ), "the poller never recorded a cycle"

        status = _status(env)
        assert status.returncode == 0
        report = json.loads(status.stdout)
        assert report["running"] is True
        assert report["pid"] == pid
        assert report["lastCycleAt"]
        assert report["stalePidfile"] is False
    finally:
        _kill(pid)

    stopped = _status(env)
    assert stopped.returncode == 1, "exit 1 is what makes it a health check"
    report = json.loads(stopped.stdout)
    assert report["running"] is False
    assert report["lastCycleAt"], "the heartbeat outlives the poller, on purpose"


def _status(env):
    return subprocess.run(
        [*CLI, "poll", "status", "--format", "json"],
        cwd=str(env["cwd"]),
        env=env["environ"],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None
