"""Unit tests for the core facade's daemon surface (issue-161, T3)."""

from types import SimpleNamespace

import pytest

from the_loop.core import daemons
from the_loop.poller.heartbeat import PollHeartbeat
from the_loop.runlock import RunLock


def _config(tmp_path):
    return {"state": {"root": str(tmp_path / ".the-loop")}}


def test_daemon_status_not_running(tmp_path):
    status = daemons.daemon_status("poller", _config(tmp_path))
    assert status == {
        "daemon": "poller",
        "running": False,
        "pid": 0,
        "pidfile": str(tmp_path / ".the-loop" / "poll.pid"),
        "logfile": str(tmp_path / ".the-loop" / "logs" / "poller.out"),
        "startedAt": "",
        "lastCycleAt": "",
    }


def test_daemon_status_running_reflects_a_held_lock(tmp_path):
    config = _config(tmp_path)
    pidfile = tmp_path / ".the-loop" / "gh-webhook.pid"
    pidfile.parent.mkdir(parents=True)
    lock = RunLock(pidfile, name="gh-webhook")
    assert lock.acquire()
    try:
        status = daemons.daemon_status("gh-webhook", config)
        assert status["running"] is True
        assert status["pid"] > 0
    finally:
        lock.release()


def test_unknown_daemon_is_value_error(tmp_path):
    with pytest.raises(ValueError):
        daemons.daemon_status("mystery", _config(tmp_path))
    with pytest.raises(ValueError):
        daemons.control_daemon("mystery", "start", _config(tmp_path))


def test_unknown_verb_is_value_error(tmp_path):
    with pytest.raises(ValueError):
        daemons.control_daemon("poller", "restart", _config(tmp_path))


# -- issue-191: the heartbeat, and a start that logs somewhere --------------------


def test_poller_status_carries_the_heartbeat(tmp_path):
    """`daemon_status` enriches liveness with when it started and last cycled."""
    config = _config(tmp_path)
    beat = PollHeartbeat(
        tmp_path / ".the-loop" / "poll-status.json", pid=4321, interval_seconds=60
    )
    beat.record(SimpleNamespace(items_seen=3, spawns=1, comments_forwarded=0))

    status = daemons.daemon_status("poller", config)
    assert status["startedAt"] and status["lastCycleAt"]
    assert status["logfile"].endswith("logs/poller.out")


def test_gh_webhook_status_reports_no_heartbeat(tmp_path):
    """The receiver keeps none — the keys are present and empty, not absent."""
    status = daemons.daemon_status("gh-webhook", _config(tmp_path))
    assert status["startedAt"] == ""
    assert status["lastCycleAt"] == ""
    assert status["logfile"].endswith("logs/gh-webhook.out")


def test_start_redirects_the_daemon_to_its_logfile(tmp_path, monkeypatch):
    """A control-plane start must not send a daemon's output to /dev/null."""
    captured = {}

    class FakePopen:
        def __init__(self, argv, stdout=None, stderr=None, stdin=None, **kwargs):
            captured["argv"] = argv
            captured["stdout"] = stdout
            captured["stderr"] = stderr
            captured["new_session"] = kwargs.get("start_new_session")
            self.pid = 9182

    monkeypatch.setattr(daemons.subprocess, "Popen", FakePopen)
    result = daemons.control_daemon("poller", "start", _config(tmp_path))

    logfile = tmp_path / ".the-loop" / "logs" / "poller.out"
    assert logfile.is_file(), "the logfile is created before the daemon is spawned"
    assert isinstance(captured["stdout"], int) and captured["stdout"] > 2
    assert captured["stdout"] == captured["stderr"]
    assert captured["new_session"] is True
    assert str(logfile) in result["output"]
