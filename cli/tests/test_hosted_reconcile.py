"""The hosted ingress set follows the config (issue-395, B5 of the e2e run).

The service composes which ingresses it hosts once, at boot; the config that decides
it is re-read forever. These tests fake each run loop at the seam the issue-334 tests
fake (``run_socket_listener``, ``poller.daemon._run_locked``) and prove the hosting:
a config edit that turns an ingress off ends its loop and releases its lock with no
restart, one that turns it on starts it with the new config, and every other edit
leaves the set alone.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from the_loop import eventlog
from the_loop.api import ingress
from the_loop.cli_config import load_cli_config
from the_loop.core import daemons as core_daemons
from the_loop.runlock import RunLock


def _write(path: Path, root: Path, *, mode="socket", slack=True, extra="") -> None:
    path.write_text(
        'version: "0.10.0"\n'
        f"state:\n  root: {root}\n"
        "channels:\n"
        "  slack:\n"
        f"    enabled: {'true' if slack else 'false'}\n"
        "    channel: C1\n"
        f"    read:\n      mode: {mode}\n"
        f"{extra}",
        encoding="utf-8",
    )


def _tokens(monkeypatch):
    monkeypatch.setenv("THE_LOOP_SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("THE_LOOP_SLACK_APP_TOKEN", "xapp-test")


def _wait(predicate, timeout=5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


@pytest.fixture
def emitted(monkeypatch):
    log = []
    monkeypatch.setattr(
        eventlog, "emit", lambda event, level="info", **f: log.append((event, f))
    )
    return log


@pytest.fixture
def listener(monkeypatch):
    """A fake Socket Mode loop: records what it was started with, waits to be stopped."""
    _tokens(monkeypatch)
    runs = []

    def fake(cli_config, stop_event=None):
        assert stop_event is not None
        runs.append({"config": cli_config, "stop": stop_event})
        stop_event.wait(10)
        return 0

    monkeypatch.setattr("the_loop.channels.slack.run_socket_listener", fake)
    return runs


def _listener_lock(config) -> RunLock:
    return RunLock(core_daemons._pidfile("slack-listener", config), name="test")


# -- T1: one composition for boot and reconcile ---------------------------------------


def test_wanted_is_the_enabled_set_in_boot_order(tmp_path):
    root = str(tmp_path / ".the-loop")
    slack = {"enabled": True, "channel": "C1", "read": {"mode": "socket"}}
    assert ingress._wanted({}) == []
    assert [n for n, _ in ingress._wanted({"polling": {"enabled": True}})] == ["poller"]
    assert [
        n for n, _ in ingress._wanted({"webhooks": {"ghWebhook": {"enabled": True}}})
    ] == ["gh-webhook"]
    assert [n for n, _ in ingress._wanted({"channels": {"slack": slack}})] == [
        "slack-listener"
    ]
    assert (
        ingress._wanted({"channels": {"slack": {**slack, "read": {"mode": "poll"}}}})
        == []
    )
    everything = {
        "state": {"root": root},
        "polling": {"enabled": True},
        "webhooks": {"ghWebhook": {"enabled": True}},
        "channels": {"slack": slack},
    }
    assert [n for n, _ in ingress._wanted(everything)] == [
        "gh-webhook",
        "poller",
        "slack-listener",
    ]


# -- T2: the supervisor over a real file -----------------------------------------------


def test_turning_read_mode_off_stops_the_hosted_listener_without_a_restart(
    tmp_path, listener, emitted
):
    """
    Feature: the hosted ingress set follows the config (issue-395)
    Scenario: read.mode goes from socket to off in the running service
        Given the service hosts the Slack listener under its own pid
        When the config file is edited to read.mode: off
        Then the listener's loop is asked to stop and its lock is released
        And ingress.hosted_stopped names the config as the reason
        And one config.reloaded names what was stopped
        And the process was never restarted
    Requirement: docs/specs/issue-395/bugfix.md R1.1, R1.4, R1.8
    """
    root = tmp_path / ".the-loop"
    path = tmp_path / "cli-config.yaml"
    _write(path, root, mode="socket")
    config = load_cli_config(path, strict=True)
    supervisor = ingress.HostedIngresses(config, path, interval=0.05)
    supervisor.start()
    try:
        assert [h.name for h in supervisor.hosted] == ["slack-listener"]
        lock = _listener_lock(config)
        assert lock.is_held() and lock.holder() == os.getpid()
        first = supervisor.hosted[0]

        _write(path, root, mode="off")

        assert _wait(lambda: not lock.is_held()), "the lock was never released"
        assert _wait(lambda: not first.thread.is_alive())
        assert listener[0]["stop"].is_set()
        assert supervisor.hosted == []
        assert (
            "ingress.hosted_stopped",
            {"ingress": "slack-listener", "reason": "config"},
        ) in [
            (e, {k: f[k] for k in ("ingress", "reason") if k in f}) for e, f in emitted
        ]
        reloaded = [f for e, f in emitted if e == "config.reloaded"]
        assert len(reloaded) == 1 and "slack-listener" in reloaded[0]["detail"]
    finally:
        supervisor.stop()


def test_turning_read_mode_back_to_socket_starts_the_listener_with_the_new_config(
    tmp_path, listener, emitted
):
    """
    Feature: the hosted ingress set follows the config (issue-395)
    Scenario: read.mode comes back to socket
        Given the service hosts nothing because read.mode is off
        When the config file is edited to read.mode: socket
        Then a listener starts under the same lock with the edited config
        And ingress.hosted is emitted for it
    Requirement: docs/specs/issue-395/bugfix.md R1.2, R1.4
    """
    root = tmp_path / ".the-loop"
    path = tmp_path / "cli-config.yaml"
    _write(path, root, mode="off")
    config = load_cli_config(path, strict=True)
    supervisor = ingress.HostedIngresses(config, path, interval=0.05)
    supervisor.start()
    try:
        assert supervisor.hosted == []
        _write(path, root, mode="socket", extra="routing:\n  authorizedUsers: [ann]\n")
        lock = _listener_lock(config)
        assert _wait(lock.is_held), "the listener never came up"
        assert lock.holder() == os.getpid()
        assert [h.name for h in supervisor.hosted] == ["slack-listener"]
        assert _wait(lambda: len(listener) == 1)
        started_with = listener[0]["config"]
        assert started_with["channels"]["slack"]["read"]["mode"] == "socket"
        assert started_with["routing"]["authorizedUsers"] == ["ann"]
        assert any(
            e == "ingress.hosted" and f.get("ingress") == "slack-listener"
            for e, f in emitted
        )
    finally:
        supervisor.stop()
    assert not lock.is_held()


def test_an_unrelated_edit_and_an_unparseable_one_leave_the_set_alone(
    tmp_path, listener, emitted
):
    """
    Feature: the hosted ingress set follows the config (issue-395)
    Scenario: edits that do not change the enabled set
        Given the service hosts the Slack listener
        When an unrelated key changes
        Then the same listener thread keeps running and no ingress event is emitted
        When the file is rewritten as invalid YAML
        Then nothing changes either
        When a valid edit turns the listener off
        Then it stops
    Requirement: docs/specs/issue-395/bugfix.md R1.3, R1.5
    """
    root = tmp_path / ".the-loop"
    path = tmp_path / "cli-config.yaml"
    _write(path, root, mode="socket")
    config = load_cli_config(path, strict=True)
    supervisor = ingress.HostedIngresses(config, path, interval=0.05)
    supervisor.start()
    try:
        first = supervisor.hosted[0]
        del emitted[:]

        _write(path, root, mode="socket", extra="routing:\n  authorizedUsers: [ann]\n")
        time.sleep(0.3)
        assert supervisor.hosted == [first] and first.thread.is_alive()
        assert not [e for e, _ in emitted if e.startswith("ingress.")]
        assert not [e for e, _ in emitted if e == "config.reloaded"]

        path.write_text("channels: [unclosed\n", encoding="utf-8")
        time.sleep(0.3)
        assert supervisor.hosted == [first] and first.thread.is_alive()
        assert not [e for e, _ in emitted if e.startswith("ingress.")]

        _write(path, root, mode="off")
        assert _wait(lambda: not first.thread.is_alive())
        assert supervisor.hosted == []
    finally:
        supervisor.stop()


def test_a_disabled_poller_is_stopped_too(tmp_path, monkeypatch, emitted):
    """
    Feature: the hosted ingress set follows the config (issue-395)
    Scenario: polling.enabled goes false
        Given the service hosts the poller
        When the config file is edited to polling.enabled: false
        Then the poller's run loop is asked to stop and its lock is released
    Requirement: docs/specs/issue-395/bugfix.md R1.1
    """
    root = tmp_path / ".the-loop"
    path = tmp_path / "cli-config.yaml"
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))

    def write(enabled: bool) -> None:
        path.write_text(
            'version: "0.10.0"\n'
            f"state:\n  root: {root}\n"
            "repositories: [octo/repo]\n"
            "polling:\n"
            f"  enabled: {'true' if enabled else 'false'}\n"
            "  sources:\n    - provider: github\n",
            encoding="utf-8",
        )

    runs = []

    def fake_run(options, stop_event=None, install_signal_handlers=True):
        assert stop_event is not None
        runs.append(stop_event)
        stop_event.wait(10)
        return 0

    monkeypatch.setattr("the_loop.poller.daemon._run_locked", fake_run)
    write(True)
    config = load_cli_config(path, strict=True)
    supervisor = ingress.HostedIngresses(config, path, interval=0.05)
    supervisor.start()
    try:
        assert [h.name for h in supervisor.hosted] == ["poller"]
        lock = RunLock(core_daemons._pidfile("poller", config), name="test")
        assert lock.is_held()
        write(False)
        assert _wait(lambda: not lock.is_held())
        assert runs[0].is_set()
        assert supervisor.hosted == []
    finally:
        supervisor.stop()


def test_shutdown_ends_the_supervisor_before_the_ingresses(tmp_path, listener):
    """
    Feature: the hosted ingress set follows the config (issue-395)
    Scenario: the service shuts down
        Given a supervisor hosting the listener
        When stop() is called
        Then the supervisor thread has ended before the listener is stopped
        And an edit after stop() starts nothing
    Requirement: docs/specs/issue-395/bugfix.md R1.6
    """
    root = tmp_path / ".the-loop"
    path = tmp_path / "cli-config.yaml"
    _write(path, root, mode="socket")
    config = load_cli_config(path, strict=True)
    supervisor = ingress.HostedIngresses(config, path, interval=0.05)
    supervisor.start()
    thread = supervisor.thread
    assert thread is not None and thread.is_alive()
    supervisor.stop()
    assert not thread.is_alive()
    assert supervisor.hosted == []
    assert not _listener_lock(config).is_held()
    _write(path, root, mode="off")
    _write(path, root, mode="socket")
    time.sleep(0.3)
    assert supervisor.hosted == [] and len(listener) == 1


def test_a_refused_start_on_reconcile_is_recorded_and_the_supervisor_survives(
    tmp_path, monkeypatch, emitted
):
    """
    Feature: the hosted ingress set follows the config (issue-395)
    Scenario: the newly wanted listener has no tokens
        Given read.mode is off and no Slack token is in the environment
        When the config file is edited to read.mode: socket
        Then ingress.hosted_failed names the missing variable, never a value
        And the supervisor keeps ticking
    Requirement: docs/specs/issue-395/bugfix.md R1.2; T8
    """
    monkeypatch.delenv("THE_LOOP_SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("THE_LOOP_SLACK_APP_TOKEN", raising=False)
    monkeypatch.setattr(
        "the_loop.channels.slack.run_socket_listener",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    root = tmp_path / ".the-loop"
    path = tmp_path / "cli-config.yaml"
    _write(path, root, mode="off")
    config = load_cli_config(path, strict=True)
    supervisor = ingress.HostedIngresses(config, path, interval=0.05)
    supervisor.start()
    try:
        _write(path, root, mode="socket")
        assert _wait(lambda: any(e == "ingress.hosted_failed" for e, _ in emitted))
        failed = [f for e, f in emitted if e == "ingress.hosted_failed"][0]
        assert failed["ingress"] == "slack-listener"
        assert "THE_LOOP_SLACK_APP_TOKEN" in failed["reason"]
        assert supervisor.hosted == []
        assert supervisor.thread is not None and supervisor.thread.is_alive()
    finally:
        supervisor.stop()


def test_reconcile_is_serialized_against_stop(tmp_path, listener):
    """A reconcile and a stop never interleave: stop() waits for the supervisor."""
    root = tmp_path / ".the-loop"
    path = tmp_path / "cli-config.yaml"
    _write(path, root, mode="socket")
    config = load_cli_config(path, strict=True)
    supervisor = ingress.HostedIngresses(config, path, interval=0.05)
    supervisor.start()
    threads = [h.thread for h in supervisor.hosted]
    _write(path, root, mode="off")
    # Race the tick: stop at once, whatever the supervisor is doing.
    supervisor.stop()
    assert supervisor.hosted == []
    assert not _listener_lock(config).is_held()
    assert all(run["stop"].is_set() for run in listener)
    assert supervisor.thread is not None and not supervisor.thread.is_alive()
    assert not any(t.is_alive() for t in threads)
