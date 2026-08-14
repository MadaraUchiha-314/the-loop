"""The poller's entry points after the ``poll`` command's removal (issue-228).

These scenarios predate issue-228 (web-terminal parity from issue-65, the
single-instance lock from issue-159, the path defaults from issue-191) and are
deliberately kept: the command that hosted them is gone, but the behaviour is
not — the run loop moved to ``the_loop.poller.daemon``, driven by
``python -m the_loop.daemon_entry poller [--once]``. Each test asserts the same
property through the new entry point.

Spec: docs/specs/issue-228/design.md §D2 (R2.2: relocated, not reimplemented).
"""

import os
from pathlib import Path

from the_loop import daemon_entry
from the_loop import runner as runner_mod
from the_loop.poller import daemon as poller_daemon
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
    # repo-local plugin config. poller.daemon resolves the path per call, so
    # chdir alone is enough — there is no cached _CONFIG_PATH to patch any more.
    (config_dir / "cli-config.yaml").write_text(CONFIG)

    FakePopen.instances = []
    monkeypatch.setattr(runner_mod.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/x")
    monkeypatch.setattr(gh_mod.shutil, "which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(gh_mod, "GhClient", FakeGhClient)


def _run_once():
    """One poll cycle through the daemon entry point — the cron form."""
    return daemon_entry.main(["poller", "--once"])


def test_poller_launches_and_stops_ttyd_like_gh_webhook_start(tmp_path, monkeypatch):
    """
    Feature: Web terminal parity across ingress paths
    Scenario: the poller drives the same ttyd lifecycle as `gh-webhook start`
        Given routing.runner: tmux and routing.webTerminal.enabled: true
        When `daemon_entry poller --once` runs a poll cycle and exits
        Then ttyd is launched for the shared tmux hub and terminated on shutdown
    Requirement: github issue #65
    """
    _configure(tmp_path, monkeypatch)

    assert _run_once() == 0
    (proc,) = FakePopen.instances
    assert proc.argv[0] == "ttyd"
    assert proc.terminated is True


def test_poller_fails_fast_when_ttyd_missing(tmp_path, monkeypatch):
    """
    Feature: Web terminal parity across ingress paths
    Scenario: the poller preflights ttyd just like `gh-webhook start`
        Given routing.webTerminal.enabled: true but ttyd is not installed
        When `daemon_entry poller --once` runs
        Then it fails fast instead of silently skipping the web terminal
    Requirement: github issue #65
    """
    _configure(tmp_path, monkeypatch)
    monkeypatch.setattr(
        runner_mod.shutil,
        "which",
        lambda binary: None if binary == "ttyd" else "/usr/bin/x",
    )

    assert _run_once() == 1
    assert FakePopen.instances == []


# -- single-instance guarantee (issue-159) --------------------------------------


def _pidfile(tmp_path):
    """Where the poller records its pid — and takes its lock.

    The configured default is relative to the process's working directory, which
    `_configure` has already pointed at ``tmp_path``.
    """
    return tmp_path / ".the-loop" / "poll.pid"


def test_poller_takes_the_lock_even_for_a_single_cycle(tmp_path, monkeypatch):
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

    assert _run_once() == 0

    assert [(Path(path).resolve(), ok) for path, ok in held] == [
        (_pidfile(tmp_path).resolve(), True)
    ]
    assert not _pidfile(tmp_path).exists()  # released on the way out


def test_poller_refuses_while_another_poller_holds_the_lock(tmp_path, monkeypatch):
    """
    Feature: at most one poller per state root
    Scenario: a restart that overlaps the poller it is replacing
        Given a poller already holds the lock on the state root's pidfile
        When a second poller is started against the same config
        Then it refuses, names the holder, and touches nothing
    Requirement: github issue #159 (AC1.1)
    """
    _configure(tmp_path, monkeypatch)
    _pidfile(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    holder = RunLock(_pidfile(tmp_path))
    assert holder.acquire()
    try:
        assert _run_once() == 1
        # Refused before anything was built: no ttyd, no ledger, and the
        # holder's own pidfile is intact.
        assert FakePopen.instances == []
        assert not (tmp_path / ".the-loop" / "portable").exists()
        assert _pidfile(tmp_path).read_text().strip() == str(os.getpid())
    finally:
        holder.release()


def test_poller_recovers_from_a_pidfile_left_by_a_crash(tmp_path, monkeypatch):
    """
    Feature: at most one poller per state root
    Scenario: the previous poller was SIGKILLed
        Given a pidfile naming a process that is not running
        When a poller runs a single cycle
        Then it starts normally — a crash needs no manual cleanup
    Requirement: github issue #159 (AC1.4)
    """
    _configure(tmp_path, monkeypatch)
    _pidfile(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    _pidfile(tmp_path).write_text("424242\n")

    assert _run_once() == 0


# -- the entry point's own surface (issue-228) ----------------------------------


def test_default_options_resolve_under_the_state_root(tmp_path, monkeypatch):
    """
    Feature: one state root configures every path the poller writes
    Scenario: no flags, no command — the config decides
        Given `state.root` is the only place generated paths are configured
        When the poller's options are resolved from the CLI config
        Then the pidfile, heartbeat and ledger all sit under that root
    Requirement: github issue #191 (R2.2, R5.1); issue #228 (R2.2)
    """
    _configure(tmp_path, monkeypatch)
    options = poller_daemon.default_options()

    root = Path(".the-loop")
    assert Path(options.pidfile) == root / "poll.pid"
    assert Path(options.status_file) == root / "poll-status.json"
    assert Path(options.state_dir) == root / "portable"
    assert options.interval == 60
    assert options.once is False


def test_daemon_entry_rejects_once_for_the_receiver(tmp_path, monkeypatch, capsys):
    """
    Feature: the daemon entry point owns the cron form
    Scenario: `--once` is a poll-cycle concept
        Given the receiver has no notion of a single cycle
        When `daemon_entry gh-webhook --once` is invoked
        Then it is rejected as a usage error (exit 2), starting nothing
    Requirement: github issue #228 (R2.3)
    """
    _configure(tmp_path, monkeypatch)
    try:
        daemon_entry.main(["gh-webhook", "--once"])
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover - argparse always raises
        raise AssertionError("expected a usage error")
    assert FakePopen.instances == []
