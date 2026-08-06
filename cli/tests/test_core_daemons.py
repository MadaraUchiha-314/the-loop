"""Unit tests for the core facade's daemon surface (issue-161, T3)."""

import pytest

from the_loop.core import daemons
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
