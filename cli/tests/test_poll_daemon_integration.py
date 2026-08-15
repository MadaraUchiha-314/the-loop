"""A detached poller, against the real process table (issue-191, re-pointed by
issue-228 when `poll start --daemon` was removed).

Everything else about the lifecycle is ordinary unit-testable code. Detaching is
not: the properties that matter — surviving the teardown of the process group
that started it, owning the pidfile's lock, logging somewhere — are statements
about the running system. So these tests spawn ``the-loop start`` (with only the
poller enabled) as a real subprocess against a temporary ``state.root``, and
then interrogate the kernel. Every test kills what it spawned in a ``finally``;
nothing here reaches the network (the ``gh`` on ``PATH`` is a stub that lists no
work items) and nothing spawns a session.

The detach idiom changed with issue-228 — `Popen(start_new_session=True)` via
``the_loop.daemon_entry`` instead of the double-fork — but the properties
asserted here are the same ones issue-191 established, minus the fork-specific
mechanics (zombie reaping) that died with the mechanism.

Spec: docs/specs/issue-191/design.md (T6, T7); docs/specs/issue-228/design.md §D2/D3.
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
    os.name != "posix", reason="daemon lifecycle tests need POSIX signals"
)

#: Only the poller is enabled: `the-loop start` must compose exactly that.
CONFIG = """
service:
  enabled: false
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
    environ.pop("THE_LOOP_SERVICE_LOCAL", None)
    return {
        "cwd": tmp_path,
        "root": root,
        "environ": environ,
        "pidfile": root / "poll.pid",
        "logfile": root / "logs" / "poller.out",
        "status": root / "poll-status.json",
    }


#: How the tests invoke the CLI. Not the console script: it is not guaranteed to
#: be on PATH in a bare checkout, and the point here is the process boundary, not
#: the packaging.
CLI = [
    sys.executable,
    "-c",
    "import sys; from the_loop.cli import main; sys.exit(main())",
]


def _cli(env, *argv, timeout=90):
    return subprocess.run(
        [*CLI, *argv],
        cwd=str(env["cwd"]),
        env=env["environ"],
        capture_output=True,
        text=True,
        timeout=timeout,
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


def test_start_detaches_a_poller_that_owns_its_pidfile_and_log(env):
    """
    Feature: `the-loop start` runs the poller as a proper daemon
    Scenario: a started poller owns its pidfile and its logfile
        Given only the poller is enabled in the CLI config
        When `the-loop start` returns
        Then it reports the poller started, the daemon holds the pidfile's
        lock in its own session, and the logfile is receiving its output
    Requirement: github issue #191 (R1.1, R2.1); issue #228 (R1.1, R1.5)
    """
    result = _cli(env, "start")
    pid = _daemon_pid(env)
    try:
        assert result.returncode == 0, result.stderr
        assert "poller" in result.stdout and "started" in result.stdout
        assert "service" in result.stdout and "disabled" in result.stdout

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


def test_a_started_poller_outlives_the_shell_that_started_it(env):
    """
    Feature: `the-loop start` runs the poller as a proper daemon
    Scenario: the poller outlives the shell that started it
        Given a poller started from a process in its own process group
        When that whole process group is torn down with SIGKILL
        Then the poller is still running and still holds its lock
    Requirement: github issue #191 (R1.2)
    """
    starter = subprocess.Popen(
        [*CLI, "start"],
        cwd=str(env["cwd"]),
        env=env["environ"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    starter.communicate(timeout=90)
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


# -- refusals and failures ------------------------------------------------------


def test_start_is_idempotent_while_the_poller_runs(env):
    """
    Feature: the pidfile tells the truth
    Scenario: a second `the-loop start` while the poller runs
        Given a poller is already running against this state root
        When `the-loop start` is invoked again
        Then it reports the poller as already running, exits 0, and the first
        poller is untouched (R1.3)
    Requirement: issue #228 (R1.3); github issue #191 (R3.3)
    """
    first = _cli(env, "start")
    pid = _daemon_pid(env)
    try:
        assert first.returncode == 0
        second = _cli(env, "start")

        assert second.returncode == 0
        assert "already-running" in second.stdout
        assert _daemon_pid(env) == pid
        assert _alive(pid), "the second start must not disturb the running poller"
    finally:
        _kill(pid)


def test_start_reports_a_startup_failure_to_its_caller(env):
    """
    Feature: an honest start
    Scenario: the poller exits during startup
        Given a config whose polling source names an unknown provider, so the
        spawned poller exits before taking its lock
        When `the-loop start` is invoked
        Then it exits non-zero, points at the logfile, and no lock is left held
    Requirement: github issue #191 (R3.4); issue #228 (R1.4, design D3)
    """
    (env["root"] / "cli-config.yaml").write_text(
        "service:\n  enabled: false\nrouting:\n  enabled: false\n"
        "polling:\n  enabled: true\n  intervalSeconds: 1\n"
        "  sources:\n    - provider: nosuch\n"
    )
    result = _cli(env, "start")

    assert result.returncode == 1
    assert "failed" in result.stdout
    assert "poller.out" in result.stdout
    assert not RunLock(env["pidfile"], name="poller").is_held()
    assert "nosuch" in env["logfile"].read_text()


def test_an_enabled_poller_with_no_sources_is_reported_at_plan_time(env):
    """
    Feature: an honest start
    Scenario: polling.enabled true with an empty sources list
        Given the config contradiction
        When `the-loop start` is invoked
        Then the poller row reads misconfigured on the terminal — not a spawn
        whose failure lands only in a logfile — and nothing is started
    Requirement: issue #228 (design D3)
    """
    (env["root"] / "cli-config.yaml").write_text(
        "service:\n  enabled: false\nrouting:\n  enabled: false\n"
        "polling:\n  enabled: true\n  sources: []\n"
    )
    result = _cli(env, "start")

    assert result.returncode == 1
    assert "misconfigured" in result.stdout
    assert "polling.sources" in result.stdout
    assert not env["pidfile"].exists()


def test_a_stale_pidfile_is_removed_by_the_next_start(env):
    """
    Feature: the pidfile tells the truth
    Scenario: a stale pidfile is cleaned up by the next start
        Given a pidfile naming a process that is not running
        When `the-loop start` brings a poller up
        Then the poller starts normally and the pidfile records the new pid
    Requirement: github issue #191 (R3.2)
    """
    env["pidfile"].parent.mkdir(parents=True, exist_ok=True)
    env["pidfile"].write_text("424242\n")

    result = _cli(env, "start")
    pid = _daemon_pid(env)
    try:
        assert result.returncode == 0, result.stderr
        assert pid not in (0, 424242)
        assert RunLock(env["pidfile"], name="poller").is_held()
    finally:
        _kill(pid)


# -- stop and status against the real daemon ------------------------------------


def test_stop_signals_the_poller_and_waits_for_it_to_exit(env):
    """
    Feature: `the-loop stop` blocks until the poller has actually exited
    Scenario: a scripted `stop && start`
        Given a running poller holding the lock
        When `the-loop stop` runs
        Then it returns success only after the lock is released (R3.1)
    Requirement: issue #228 (R3.1); github issue #159 (AC2.2)
    """
    assert _cli(env, "start").returncode == 0
    pid = _daemon_pid(env)
    try:
        result = _cli(env, "stop")
        assert result.returncode == 0
        assert "stopped" in result.stdout
        assert not RunLock(env["pidfile"], name="poller").is_held()
        # The lock is released in the daemon's `finally`, a moment before the
        # process itself finishes dying — wait for the tail end.
        assert _wait_for(lambda: not _alive(pid), timeout=10)
    finally:
        _kill(pid)


def test_status_reports_a_running_poller_its_pid_and_its_last_cycle(env):
    """
    Feature: `the-loop status` answers "is the poller actually running?"
    Scenario: status reports a running poller, its pid and its last cycle
        Given a poller started by `the-loop start`
        When `the-loop status --format json` runs after the first cycle
        Then the poller row carries running=true, the daemon's real pid, and
        the last cycle's counters
    Requirement: github issue #191 (R4); issue #228 (R2.4, R3.2)
    """
    assert _cli(env, "start").returncode == 0
    pid = _daemon_pid(env)
    try:
        assert _wait_for(
            lambda: (
                env["status"].is_file()
                and json.loads(env["status"].read_text()).get("lastCycleAt")
            )
        )
        result = _cli(env, "status", "--format", "json")
        assert result.returncode == 0, result.stdout
        report = json.loads(result.stdout)
        row = next(r for r in report["services"] if r["service"] == "poller")
        assert row["running"] is True
        assert row["pid"] == pid
        assert row["enabled"] is True
        assert row["lastCycleAt"]
        assert "itemsSeen" in row["lastCycle"]
    finally:
        _kill(pid)
