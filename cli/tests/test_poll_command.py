"""``poll start`` CLI wiring (issue-65).

Before this fix, ``routing.webTerminal.enabled`` only launched ttyd from
``gh-webhook start`` — ``poll start`` shared the same tmux runner but had no
ttyd start/stop of its own, so the web terminal was silently absent when
polling was the ingress. These tests drive the real ``poll start`` command
(argparse included) and assert ttyd is spawned and stopped exactly as it is
for ``gh-webhook start``.

Spec: docs/specs/issue-34/design.md (poller shares the webhook routing stack).
"""

import os
from pathlib import Path

from the_loop import runner as runner_mod
from the_loop.cli import build_parser
from the_loop.commands import gh_webhook, poll
from the_loop.poller import github as gh_mod
from the_loop.poller.heartbeat import PollHeartbeat
from the_loop.runlock import RunLock

CONFIG = """
routing:
  enabled: true
  runner: tmux
  webTerminal:
    enabled: true
    host: 127.0.0.1
    port: 7681
  authorizedUsers: ["octocat"]
polling:
  intervalSeconds: 60
  sources:
    - provider: github
      repos: ["octo/repo"]
"""


class FakePopen:
    """Stand-in for subprocess.Popen recording argv, no real process spawned."""

    instances = []

    def __init__(self, argv):
        self.argv = argv
        self.terminated = False
        FakePopen.instances.append(self)

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        pass

    def kill(self):
        pass


class FakeGhClient:
    """Stand-in for GhClient: no `gh` binary needed, no items discovered."""

    def __init__(self, binary="gh", **_kwargs):
        self.binary = binary

    def is_available(self):
        return True

    def list_labeled_issues(self, owner, repo, label):
        return []

    def list_labeled_prs(self, owner, repo, label):
        return []


def _configure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".the-loop"
    config_dir.mkdir()
    # webhooks/polling live in the CLI config (issue-63, decision-032), not the
    # repo-local plugin config.
    cli_config_path = config_dir / "cli-config.yaml"
    cli_config_path.write_text(CONFIG)
    monkeypatch.setattr(gh_webhook, "_CONFIG_PATH", cli_config_path)
    monkeypatch.setattr(poll, "_CONFIG_PATH", cli_config_path)

    FakePopen.instances = []
    monkeypatch.setattr(runner_mod.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/x")
    monkeypatch.setattr(gh_mod.shutil, "which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(gh_mod, "GhClient", FakeGhClient)


def test_poll_start_launches_and_stops_ttyd_like_gh_webhook_start(
    tmp_path, monkeypatch
):
    """
    Feature: Web terminal parity across ingress paths
    Scenario: `poll start` drives the same ttyd lifecycle as `gh-webhook start`
        Given routing.runner: tmux and routing.webTerminal.enabled: true
        When `poll start --once` runs a poll cycle and exits
        Then ttyd is launched for the shared tmux hub and terminated on shutdown
    Requirement: github issue #65
    """
    _configure(tmp_path, monkeypatch)

    parser = build_parser()
    args = parser.parse_args(["poll", "start", "--once"])
    exit_code = args._action(args)

    assert exit_code == 0
    (proc,) = FakePopen.instances
    assert proc.argv[0] == "ttyd"
    assert proc.terminated is True


def test_poll_start_fails_fast_when_ttyd_missing(tmp_path, monkeypatch):
    """
    Feature: Web terminal parity across ingress paths
    Scenario: `poll start` preflights ttyd just like `gh-webhook start`
        Given routing.webTerminal.enabled: true but ttyd is not installed
        When `poll start --once` runs
        Then it fails fast instead of silently skipping the web terminal
    Requirement: github issue #65
    """
    _configure(tmp_path, monkeypatch)
    monkeypatch.setattr(
        runner_mod.shutil,
        "which",
        lambda binary: None if binary == "ttyd" else "/usr/bin/x",
    )

    parser = build_parser()
    args = parser.parse_args(["poll", "start", "--once"])
    exit_code = args._action(args)

    assert exit_code == 1
    assert FakePopen.instances == []


# -- single-instance guarantee and a truthful `stop` (issue-159) ---------------


def _pidfile(tmp_path):
    """Where `poll start` records its pid — and now takes its lock.

    The configured default is relative to the process's working directory, which
    `_configure` has already pointed at ``tmp_path``.
    """
    return tmp_path / ".the-loop" / "poll.pid"


def test_poll_start_takes_the_lock_even_for_a_single_cycle(tmp_path, monkeypatch):
    """
    Feature: at most one poller per state root
    Scenario: `--once` participates in the exclusion
        Given a poller is started with `--once`
        When the cycle runs and the process exits
        Then the lock was held for the run and the pidfile is removed afterwards
    Requirement: github issue #159 (AC1.2)
    """
    _configure(tmp_path, monkeypatch)
    held = []
    real_acquire = RunLock.acquire

    def watching_acquire(self):
        ok = real_acquire(self)
        held.append((str(self.path), ok))
        return ok

    monkeypatch.setattr(RunLock, "acquire", watching_acquire)

    args = build_parser().parse_args(["poll", "start", "--once"])
    assert args._action(args) == 0

    assert [(Path(path).resolve(), ok) for path, ok in held] == [
        (_pidfile(tmp_path).resolve(), True)
    ]
    assert not _pidfile(tmp_path).exists()  # released on the way out


def test_poll_start_refuses_while_another_poller_holds_the_lock(tmp_path, monkeypatch):
    """
    Feature: at most one poller per state root
    Scenario: a restart that overlaps the poller it is replacing
        Given a poller already holds the lock on the state root's pidfile
        When a second `poll start` is invoked against the same config
        Then it refuses, names the holder, and touches nothing
    Requirement: github issue #159 (AC1.1)
    """
    _configure(tmp_path, monkeypatch)
    _pidfile(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    holder = RunLock(_pidfile(tmp_path))
    assert holder.acquire()
    try:
        args = build_parser().parse_args(["poll", "start", "--once"])
        assert args._action(args) == 1
        # Refused before anything was built: no ttyd, no ledger, and the
        # holder's own pidfile is intact.
        assert FakePopen.instances == []
        assert not (tmp_path / ".the-loop" / "portable").exists()
        assert _pidfile(tmp_path).read_text().strip() == str(os.getpid())
    finally:
        holder.release()


def test_poll_start_recovers_from_a_pidfile_left_by_a_crash(tmp_path, monkeypatch):
    """
    Feature: at most one poller per state root
    Scenario: the previous poller was SIGKILLed
        Given a pidfile naming a process that is not running
        When `poll start --once` is invoked
        Then it starts normally — a crash needs no manual cleanup
    Requirement: github issue #159 (AC1.4)
    """
    _configure(tmp_path, monkeypatch)
    _pidfile(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    _pidfile(tmp_path).write_text("424242\n")

    args = build_parser().parse_args(["poll", "start", "--once"])
    assert args._action(args) == 0


def test_poll_stop_refuses_to_signal_a_stale_pidfile(tmp_path, monkeypatch):
    """
    Feature: `stop` is verified before it signals
        Scenario: a pidfile whose pid now belongs to somebody else
        Given a pidfile left behind by a killed poller
        When `poll stop` runs
        Then no signal is sent, the stale pidfile is removed, and it exits non-zero
    Requirement: github issue #159 (AC2.1)
    """
    _configure(tmp_path, monkeypatch)
    pidfile = _pidfile(tmp_path)
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    pidfile.write_text(f"{os.getpid()}\n")  # a LIVE pid that is not a poller

    signalled = []
    monkeypatch.setattr(poll.os, "kill", lambda pid, sig: signalled.append((pid, sig)))

    args = build_parser().parse_args(["poll", "stop"])
    assert args._action(args) == 1
    assert signalled == []
    assert not pidfile.exists()


def test_poll_stop_signals_the_holder_and_waits_for_it_to_go(tmp_path, monkeypatch):
    """
    Feature: `stop` blocks until the poller has actually exited
        Scenario: a scripted `stop && start`
        Given a running poller holding the lock
        When `poll stop` signals it and the poller releases the lock
        Then `stop` returns success only after the release
    Requirement: github issue #159 (AC2.2)
    """
    _configure(tmp_path, monkeypatch)
    pidfile = _pidfile(tmp_path)
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    holder = RunLock(pidfile)
    assert holder.acquire()

    # The "poller" reacts to the signal the way the real one does: it exits,
    # which releases the lock.
    monkeypatch.setattr(poll.os, "kill", lambda pid, sig: holder.release())

    args = build_parser().parse_args(["poll", "stop"])
    assert args._action(args) == 0
    assert not pidfile.exists()


def test_poll_stop_reports_a_poller_that_outlives_the_timeout(tmp_path, monkeypatch):
    """
    Feature: `stop` blocks until the poller has actually exited
        Scenario: the poller is draining a long dispatch
        Given a running poller that does not exit
        When `poll stop --timeout` runs out
        Then it exits non-zero rather than reporting a success that has not happened
    Requirement: github issue #159 (AC2.3)
    """
    _configure(tmp_path, monkeypatch)
    pidfile = _pidfile(tmp_path)
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    holder = RunLock(pidfile)
    assert holder.acquire()
    monkeypatch.setattr(poll.os, "kill", lambda pid, sig: None)  # ignores it
    try:
        args = build_parser().parse_args(["poll", "stop", "--timeout", "0.2"])
        assert args._action(args) == 1
        assert pidfile.exists()  # still running — nothing is cleaned up
    finally:
        holder.release()


def test_poll_stop_without_a_pidfile_is_unchanged(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    args = build_parser().parse_args(["poll", "stop"])
    assert args._action(args) == 1


# -- daemon options and their preflight (issue-191) ----------------------------


def test_daemon_and_foreground_are_one_setting(tmp_path, monkeypatch):
    """
    Feature: `poll start` detaches on request
    Scenario: the two spellings are one setting, last flag wins
        Given `--daemon` and `--foreground` name the same option
        When both appear on one command line
        Then the last one decides, so a wrapper script can force either
    Requirement: github issue #191 (R1.3, R1.4)
    """
    _configure(tmp_path, monkeypatch)
    parse = build_parser().parse_args

    assert parse(["poll", "start"]).daemon is False
    assert parse(["poll", "start", "--daemon"]).daemon is True
    assert parse(["poll", "start", "--daemon", "--foreground"]).daemon is False
    assert parse(["poll", "start", "--foreground", "--daemon"]).daemon is True


def test_daemon_paths_default_under_the_state_root(tmp_path, monkeypatch):
    """
    Feature: `poll start` detaches on request
    Scenario: one root configures every path the daemon writes
        Given `state.root` is the only place generated paths are configured
        When `poll start` is parsed with no path flags
        Then the logfile, pidfile and heartbeat all resolve under that root
    Requirement: github issue #191 (R2.2, R5.1)
    """
    _configure(tmp_path, monkeypatch)
    args = build_parser().parse_args(["poll", "start"])

    root = Path(".the-loop")
    assert Path(args.logfile) == root / "logs" / "poller.out"
    assert Path(args.pidfile) == root / "poll.pid"
    assert Path(args.status_file) == root / "poll-status.json"


def test_daemon_with_once_is_refused(tmp_path, monkeypatch):
    """
    Feature: `poll start` detaches on request
    Scenario: detaching a single cycle is refused, not silently honoured
        Given `--once` exists so cron and systemd can see the exit code
        When `--daemon --once` is invoked
        Then it exits 2 naming the conflict, and never forks
    Requirement: github issue #191 (R1.5)
    """
    _configure(tmp_path, monkeypatch)
    args = build_parser().parse_args(["poll", "start", "--daemon", "--once"])

    assert args._action(args) == 2
    assert not (tmp_path / ".the-loop" / "poll.pid").exists()


def test_daemon_start_refuses_before_forking_when_the_lock_is_held(
    tmp_path, monkeypatch
):
    """
    Feature: `poll start` detaches on request
    Scenario: a refusal reaches the terminal, not a logfile nobody has opened
        Given another poller already holds the lock
        When `poll start --daemon` is invoked
        Then it refuses in the foreground, naming the holding pid, without forking
    Requirement: github issue #191 (R3.3)
    """
    _configure(tmp_path, monkeypatch)
    pidfile = tmp_path / ".the-loop" / "poll.pid"
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    holder = RunLock(pidfile)
    assert holder.acquire()
    forked = []
    monkeypatch.setattr(poll, "daemonize", lambda *a, **k: forked.append(a) or 0)
    try:
        args = build_parser().parse_args(["poll", "start", "--daemon"])
        assert args._action(args) == 1
        assert forked == [], "the fork must not happen after a refusal"
    finally:
        holder.release()


def test_daemon_start_fails_when_the_logfile_cannot_be_opened(tmp_path, monkeypatch):
    """
    Feature: `poll start` detaches on request
    Scenario: a daemon whose output has nowhere to go never starts
        Given the logfile's parent path is a file rather than a directory
        When `poll start --daemon` is invoked
        Then it fails in the foreground with the reason, and never forks
    Requirement: github issue #191 (R2.4)
    """
    _configure(tmp_path, monkeypatch)
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    forked = []
    monkeypatch.setattr(poll, "daemonize", lambda *a, **k: forked.append(a) or 0)

    args = build_parser().parse_args(
        ["poll", "start", "--daemon", "--logfile", str(blocker / "poller.out")]
    )
    assert args._action(args) == 1
    assert forked == []


def test_a_stale_pidfile_is_removed_by_the_next_start(tmp_path, monkeypatch):
    """
    Feature: the pidfile tells the truth
    Scenario: a pidfile left by a killed poller is cleaned up, not inherited
        Given a pidfile naming a pid nothing holds a lock for
        When `poll start --once` runs
        Then the stale file is removed and the run takes a fresh lock
    Requirement: github issue #191 (R3.2)
    """
    _configure(tmp_path, monkeypatch)
    pidfile = tmp_path / ".the-loop" / "poll.pid"
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    pidfile.write_text("999999\n")

    args = build_parser().parse_args(["poll", "start", "--once"])
    assert args._action(args) == 0
    assert not pidfile.exists()


def test_the_poller_records_a_heartbeat_for_the_cycle_it_ran(tmp_path, monkeypatch):
    """
    Feature: `poll status` reports progress, not only liveness
    Scenario: every cycle leaves a heartbeat behind
        Given a poller that completes one cycle and exits
        When the run finishes
        Then the heartbeat records when it started and when it last cycled
    Requirement: github issue #191 (R4.5)
    """
    _configure(tmp_path, monkeypatch)
    args = build_parser().parse_args(["poll", "start", "--once"])
    assert args._action(args) == 0

    beat = PollHeartbeat.read(tmp_path / ".the-loop" / "poll-status.json")
    assert beat is not None
    assert beat.started_at and beat.last_cycle_at
    assert beat.last_cycle["itemsSeen"] == 0  # FakeGhClient discovers nothing


def test_daemon_entry_never_daemonizes(tmp_path, monkeypatch):
    """
    Feature: the control plane starts daemons itself
    Scenario: a control-plane start does not double-fork
        Given `core.daemons` already detached the process it spawned
        When `the_loop.daemon_entry` builds the poller's option namespace
        Then `daemon` is false, whatever the flag's default happens to be
    Requirement: github issue #191 (R2.5)
    """
    _configure(tmp_path, monkeypatch)
    from the_loop import daemon_entry

    assert daemon_entry._namespace("poller").daemon is False
