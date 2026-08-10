"""``the-loop poll status`` — one command instead of a ps/pidfile/log cross-check
(issue-191, T2 and the T7 abuse cases).

The invariant every test here defends is the same one: **liveness comes from the
lock, never from the heartbeat**. The lock is immune to pid reuse and cannot be
forged by writing a file; the heartbeat is a claim, useful for progress and
nothing else. So a heartbeat with no poller behind it reads *not running*, and a
poller with no heartbeat still reads *running*.

The exit code is part of the contract, not a detail: `poll status` is meant to be
the health check a keepalive is built on, which is why it exits `1` when no
poller holds the lock.

Spec: docs/specs/issue-191/design.md; testing plan row T2.
"""

import json

import pytest

from the_loop.cli import build_parser
from the_loop.poller.heartbeat import PollHeartbeat
from the_loop.runlock import RunLock


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / ".the-loop"
    root.mkdir()
    return {
        "pidfile": root / "poll.pid",
        "status": root / "poll-status.json",
        "logfile": root / "logs" / "poller.out",
    }


def _run(paths, *extra):
    parser = build_parser()
    args = parser.parse_args(
        [
            "poll",
            "status",
            "--pidfile",
            str(paths["pidfile"]),
            "--status-file",
            str(paths["status"]),
            "--logfile",
            str(paths["logfile"]),
            *extra,
        ]
    )
    return args._action(args)


def _record(paths, **kwargs):
    from types import SimpleNamespace

    summary = SimpleNamespace(
        items_seen=kwargs.pop("items_seen", 5),
        spawns=kwargs.pop("spawns", 1),
        comments_forwarded=kwargs.pop("comments_forwarded", 0),
        closures=0,
        failures=0,
        errors=[],
        interrupted=False,
    )
    PollHeartbeat(paths["status"], **kwargs).record(summary)


# -- liveness -------------------------------------------------------------------


def test_a_held_lock_reports_running_and_exits_zero(paths, capsys):
    lock = RunLock(paths["pidfile"], name="poller")
    assert lock.acquire()
    try:
        assert _run(paths) == 0
    finally:
        lock.release()
    out = capsys.readouterr().out
    assert "poller:     running (pid" in out
    assert "stale" not in out


def test_no_pidfile_reports_not_running_and_exits_one(paths, capsys):
    assert _run(paths) == 1
    assert "poller:     not running" in capsys.readouterr().out


def test_a_stale_pidfile_is_reported_and_left_alone(paths, capsys):
    """R4.4 / T7: named as stale — and NOT deleted by a read-only command."""
    paths["pidfile"].write_text("999999\n")

    assert _run(paths) == 1
    out = capsys.readouterr().out
    assert "not running" in out
    assert "stale — pid 999999 is not running" in out
    assert paths["pidfile"].is_file(), "status reports; start and stop remove"


def test_a_forged_heartbeat_cannot_make_a_dead_poller_look_alive(paths, capsys):
    """T7 abuse case: liveness is the lock, never the file."""
    _record(paths, pid=4242)  # a heartbeat with no poller behind it

    assert _run(paths) == 1
    out = capsys.readouterr().out
    assert "poller:     not running" in out
    assert "before it stopped" in out


# -- progress -------------------------------------------------------------------


def test_the_last_cycle_is_reported_with_its_age_and_counters(paths, capsys):
    _record(paths, pid=4242, interval_seconds=60)
    lock = RunLock(paths["pidfile"], name="poller")
    assert lock.acquire()
    try:
        assert _run(paths) == 0
    finally:
        lock.release()

    out = capsys.readouterr().out
    assert "last cycle:" in out
    assert "ago) — 5 item(s), 1 spawn(s), 0 comment(s) forwarded" in out
    assert "before it stopped" not in out


def test_a_started_poller_with_no_cycle_yet_says_so(paths, capsys):
    PollHeartbeat(paths["status"], pid=4242).record(None)

    assert _run(paths) == 1
    assert "last cycle: none recorded yet" in capsys.readouterr().out


def test_heartbeat_absent_still_reports_liveness(paths, capsys):
    """R4.8 / T14: a poller from before the heartbeat existed is still readable."""
    lock = RunLock(paths["pidfile"], name="poller")
    assert lock.acquire()
    try:
        assert _run(paths) == 0
    finally:
        lock.release()

    out = capsys.readouterr().out
    assert "poller:     running (pid" in out
    assert "last cycle: unknown — no heartbeat at" in out


def test_an_unreadable_heartbeat_is_treated_as_absent(paths, capsys):
    paths["status"].write_text("{ truncated")

    assert _run(paths) == 1
    assert "no heartbeat at" in capsys.readouterr().out


# -- json -----------------------------------------------------------------------


def test_json_carries_the_same_facts(paths, capsys):
    _record(paths, pid=4242, interval_seconds=60)
    lock = RunLock(paths["pidfile"], name="poller")
    assert lock.acquire()
    try:
        assert _run(paths, "--format", "json") == 0
    finally:
        lock.release()

    report = json.loads(capsys.readouterr().out)
    assert report["daemon"] == "poller"
    assert report["running"] is True
    assert report["pid"] > 0
    assert report["stalePidfile"] is False
    assert report["lastCycle"]["itemsSeen"] == 5
    assert report["intervalSeconds"] == 60
    assert report["logfile"] == str(paths["logfile"])
    assert report["statusFile"] == str(paths["status"])


def test_json_reports_a_stale_pidfile_without_claiming_a_pid(paths, capsys):
    paths["pidfile"].write_text("999999\n")

    assert _run(paths, "--format", "json") == 1
    report = json.loads(capsys.readouterr().out)
    assert report["running"] is False
    assert report["pid"] == 0, "pid is what is *running*, and nothing is"
    assert report["stalePidfile"] is True
    assert report["recordedPid"] == 999999
