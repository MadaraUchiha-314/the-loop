"""The Slack Socket Mode listener hosted by the service (issue-334, R2.7).

The listener's own loop is faked at its one seam (``run_socket_listener``), so
what is proved is the hosting: the lock under this process's pid, the stop
through the stop event, and the lock's release when the loop ends on its own.
"""

from __future__ import annotations

import os
import threading

from the_loop.api import ingress
from the_loop.core import daemons as core_daemons
from the_loop.runlock import RunLock


def _config(tmp_path, mode="socket", enabled=True):
    return {
        "state": {"root": str(tmp_path / ".the-loop")},
        "channels": {
            "slack": {"enabled": enabled, "channel": "C1", "read": {"mode": mode}}
        },
    }


def _tokens(monkeypatch):
    monkeypatch.setenv("THE_LOOP_SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("THE_LOOP_SLACK_APP_TOKEN", "xapp-test")


def test_the_service_hosts_the_listener_under_its_own_pid(tmp_path, monkeypatch):
    """
    Feature: single-process mode (service.hostIngresses)
    Scenario: start_hosted_ingresses with channels.slack in socket mode
        Given both tokens and read.mode: socket
        When the hosted ingresses start
        Then the listener's loop runs on a thread with a stop event
        And its pidfile lock is held by this process
        And stopping the hosted ingresses ends the loop and releases the lock
    Requirement: docs/specs/issue-334/requirements.md R2.7
    """
    _tokens(monkeypatch)
    seen = {}

    def fake_listener(cli_config, stop_event=None):
        assert stop_event is not None
        seen["config"] = cli_config
        seen["stop_event"] = stop_event
        stop_event.wait(5)
        return 0

    monkeypatch.setattr("the_loop.channels.slack.run_socket_listener", fake_listener)
    config = _config(tmp_path)
    hosted = ingress.start_hosted_ingresses(config)
    assert [h.name for h in hosted] == ["slack-listener"]
    lock = RunLock(core_daemons._pidfile("slack-listener", config), name="x")
    assert lock.is_held() and lock.holder() == os.getpid()
    assert seen["config"] is config and isinstance(seen["stop_event"], threading.Event)
    ingress.stop_hosted_ingresses(hosted)
    assert not hosted[0].thread.is_alive()
    assert not lock.is_held()


def test_a_listener_that_exits_on_its_own_releases_its_lock(tmp_path, monkeypatch):
    _tokens(monkeypatch)
    monkeypatch.setattr(
        "the_loop.channels.slack.run_socket_listener",
        lambda cli_config, stop_event=None: (_ for _ in ()).throw(RuntimeError("x")),
    )
    config = _config(tmp_path)
    hosted = ingress.start_hosted_ingresses(config)
    assert len(hosted) == 1
    hosted[0].thread.join(5)
    assert not RunLock(
        core_daemons._pidfile("slack-listener", config), name="x"
    ).is_held()
    ingress.stop_hosted_ingresses(hosted)  # safe after the self-release


def test_poll_mode_or_a_disabled_channel_hosts_nothing(tmp_path, monkeypatch):
    _tokens(monkeypatch)
    monkeypatch.setattr(
        "the_loop.channels.slack.run_socket_listener",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    assert ingress.start_hosted_ingresses(_config(tmp_path, mode="poll")) == []
    assert ingress.start_hosted_ingresses(_config(tmp_path, enabled=False)) == []


def test_missing_tokens_refuse_to_host_loudly(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("THE_LOOP_SLACK_BOT_TOKEN", raising=False)
    monkeypatch.setenv("THE_LOOP_SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.setattr(
        "the_loop.channels.slack.run_socket_listener",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    with caplog.at_level("ERROR", logger="the-loop.service"):
        assert ingress.start_hosted_ingresses(_config(tmp_path)) == []
    assert "THE_LOOP_SLACK_BOT_TOKEN" in caplog.text
    config = _config(tmp_path)
    assert not RunLock(
        core_daemons._pidfile("slack-listener", config), name="x"
    ).is_held()


def test_a_held_lock_is_not_fought_over(tmp_path, monkeypatch, caplog):
    _tokens(monkeypatch)
    config = _config(tmp_path)
    (tmp_path / ".the-loop").mkdir(parents=True)
    other = RunLock(
        core_daemons._pidfile("slack-listener", config), name="slack-listener"
    )
    assert other.acquire()
    monkeypatch.setattr(
        "the_loop.channels.slack.run_socket_listener",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    try:
        with caplog.at_level("WARNING", logger="the-loop.service"):
            assert ingress.start_hosted_ingresses(config) == []
    finally:
        other.release()
    assert "already running" in caplog.text


def test_channels_listen_refuses_when_a_listener_holds_the_lock(
    tmp_path, monkeypatch, capsys
):
    """The foreground form takes the same lock the service does (issue-334)."""
    import argparse
    import json

    from the_loop.commands.channels_cmd import ChannelsCommand

    config = _config(tmp_path)
    (tmp_path / ".the-loop").mkdir(parents=True)
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    (tmp_path / "cli-config.yaml").write_text(json.dumps(config), encoding="utf-8")
    holder = RunLock(
        core_daemons._pidfile("slack-listener", config), name="slack-listener"
    )
    assert holder.acquire()
    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    try:
        code = ChannelsCommand().run(parser.parse_args(["listen"]))
    finally:
        holder.release()
    assert code == 1
    assert "already running" in capsys.readouterr().err
