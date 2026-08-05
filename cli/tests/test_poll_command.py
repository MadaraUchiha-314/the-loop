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
