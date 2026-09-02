"""``the-loop status`` on the poller — the ps/pidfile/log cross-check replacement
(issue-191, re-pointed by issue-228 when `poll status` was removed).

The invariant every test here defends is unchanged: **liveness and the pid come
from the lock, never from the heartbeat**. The lock is immune to pid reuse and
cannot be forged by writing a file; the heartbeat is a claim, useful for progress
and nothing else. So a heartbeat with no poller behind it reads *not running*, and
a poller with no heartbeat still reads *running*. Since issue-205 the heartbeat
carries no pid at all — the last test here pins that a leftover one from an older
poller is still ignored.

The exit code is part of the contract, not a detail: `the-loop status` exits 0
iff every *enabled* service is running (R3.3), so these tests enable only the
poller — its liveness alone decides the code, exactly as `poll status`'s did.

Spec: docs/specs/issue-191/design.md (row T2); docs/specs/issue-205/requirements.md
(row T4); docs/specs/issue-228/requirements.md (R2.4, R3.2–R3.4).
"""

import json
import os
from pathlib import Path

import pytest

from the_loop.cli import main
from the_loop.poller.heartbeat import PollHeartbeat
from the_loop.runlock import RunLock

#: Only the poller is enabled, so its liveness alone decides the exit code.
CONFIG = "service:\n  enabled: false\npolling:\n  enabled: true\n"


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / ".the-loop"
    root.mkdir()
    (root / "cli-config.yaml").write_text(CONFIG)
    return {
        "pidfile": root / "poll.pid",
        "status": root / "poll-status.json",
    }


def _run(*extra):
    return main(["status", *extra])


def _poller_row(capsys):
    report = json.loads(capsys.readouterr().out)
    return next(r for r in report["services"] if r["service"] == "poller")


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
        assert _run() == 0
    finally:
        lock.release()
    out = capsys.readouterr().out
    assert "poller" in out and "running (pid" in out


def test_no_pidfile_reports_not_running_and_exits_one(paths, capsys):
    assert _run() == 1
    assert "not running" in capsys.readouterr().out


def test_a_stale_pidfile_is_reported_and_left_alone(paths, capsys):
    """R4.4 / T7: read as not running — and NOT deleted by a read-only command."""
    paths["pidfile"].write_text("999999\n")

    assert _run() == 1
    assert "not running" in capsys.readouterr().out
    assert paths["pidfile"].is_file(), "status reports; start and stop remove"


def test_a_forged_heartbeat_cannot_make_a_dead_poller_look_alive(paths, capsys):
    """T7 abuse case: liveness is the lock, never the file."""
    _record(paths)  # a heartbeat with no poller behind it

    assert _run() == 1
    out = capsys.readouterr().out
    assert "not running" in out
    assert "before it stopped" in out


# -- progress -------------------------------------------------------------------


def test_the_last_cycle_is_reported_with_its_age_and_counters(paths, capsys):
    _record(paths, interval_seconds=60)
    lock = RunLock(paths["pidfile"], name="poller")
    assert lock.acquire()
    try:
        assert _run() == 0
    finally:
        lock.release()

    out = capsys.readouterr().out
    assert "last cycle:" in out
    assert "ago) — 5 item(s), 1 spawn(s), 0 comment(s) forwarded" in out
    assert "before it stopped" not in out


def test_a_started_poller_with_no_cycle_yet_says_so(paths, capsys):
    PollHeartbeat(paths["status"]).record(None)

    assert _run() == 1
    assert "last cycle: none recorded yet" in capsys.readouterr().out


def test_heartbeat_absent_still_reports_liveness(paths, capsys):
    """R4.8 / T14: a poller from before the heartbeat existed is still readable."""
    lock = RunLock(paths["pidfile"], name="poller")
    assert lock.acquire()
    try:
        assert _run() == 0
    finally:
        lock.release()

    out = capsys.readouterr().out
    assert "running (pid" in out
    assert "no heartbeat" in out


def test_an_unreadable_heartbeat_is_treated_as_absent(paths, capsys):
    paths["status"].write_text("{ truncated")

    assert _run() == 1
    assert "no heartbeat" in capsys.readouterr().out


# -- json -----------------------------------------------------------------------


def test_json_carries_the_same_facts(paths, capsys):
    _record(paths, interval_seconds=60)
    lock = RunLock(paths["pidfile"], name="poller")
    assert lock.acquire()
    try:
        assert _run("--format", "json") == 0
    finally:
        lock.release()

    row = _poller_row(capsys)
    assert row["running"] is True
    assert row["pid"] > 0
    assert row["enabled"] is True
    assert row["lastCycle"]["itemsSeen"] == 5
    assert row["intervalSeconds"] == 60
    assert Path(row["pidfile"]).resolve() == paths["pidfile"].resolve()
    assert row["logfile"]


def test_json_reports_a_stale_pidfile_without_claiming_a_pid(paths, capsys):
    paths["pidfile"].write_text("999999\n")

    assert _run("--format", "json") == 1
    row = _poller_row(capsys)
    assert row["running"] is False
    assert row["pid"] == 0, "pid is what is *running*, and nothing is"


def test_a_pid_left_in_an_older_heartbeat_is_never_reported(paths, capsys):
    """issue-205 abuse case 2: a pid in that file names nothing, live or not.

    `os.getpid()` is deliberately a **live** process — the pid an older poller
    would have left behind, or a hostile writer would choose. It must not reach
    the report, where an operator could signal it.
    """
    paths["status"].write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "startedAt": "2026-08-10T09:00:00Z",
                "lastCycleAt": "2026-08-10T09:01:00Z",
                "intervalSeconds": 60,
                "lastCycle": {"itemsSeen": 3},
            }
        )
    )

    assert _run("--format", "json") == 1
    row = _poller_row(capsys)
    assert row["running"] is False
    assert row["pid"] == 0


# -- degraded scopes (issue-315) ----------------------------------------------


def _degraded(paths, **counters):
    from types import SimpleNamespace

    def scope(s, error, permanent=False):
        return SimpleNamespace(scope=s, error=error, permanent=permanent)

    summary = SimpleNamespace(
        items_seen=counters.pop("items_seen", 24),
        spawns=0,
        comments_forwarded=1,
        closures=0,
        failures=0,
        errors=["octo/repo-m: the 'octo/repo-m' repository has disabled issues"],
        interrupted=False,
        scopes_failed=[
            scope(
                "octo/repo-m",
                "gh issue list --repo exited 1: the 'octo/repo-m' repository has disabled issues",
                True,
            )
        ],
        scopes_skipped=[
            scope("octo/repo-z", "issues are disabled on this repository", True)
        ],
        scopes_polled=counters.pop("scopes_polled", 12),
    )
    PollHeartbeat(paths["status"], interval_seconds=60).record(summary)


def test_a_degraded_scope_is_named_beneath_the_last_cycle(paths, capsys):
    """R3.2: one `degraded:` line per scope, with its reason."""
    _degraded(paths)
    lock = RunLock(paths["pidfile"], name="poller")
    assert lock.acquire()
    try:
        assert _run() == 0  # R3.4: degraded is still running
    finally:
        lock.release()

    out = capsys.readouterr().out
    assert "24 item(s), 0 spawn(s), 1 comment(s) forwarded, 1 error(s)" in out
    lines = [line.strip() for line in out.splitlines() if "degraded:" in line]
    assert lines == [
        "degraded:   octo/repo-m — listing failed, permanent: gh issue list --repo "
        "exited 1: the 'octo/repo-m' repository has disabled issues",
        "degraded:   octo/repo-z — issues are disabled on this repository",
    ]
    assert "no repository was polled" not in out


def test_a_cycle_where_nothing_answered_says_so(paths, capsys):
    """R3.3: zero scopes polled is written in words, not left to `0 item(s)`."""
    _degraded(paths, items_seen=0, scopes_polled=0)
    _run()
    out = capsys.readouterr().out
    assert "degraded:   no repository was polled — every listing failed" in out


def test_a_clean_cycle_prints_no_degraded_line(paths, capsys):
    _record(paths, interval_seconds=60)
    _run()
    assert "degraded" not in capsys.readouterr().out


def test_json_carries_the_degraded_scopes(paths, capsys):
    _degraded(paths)
    _run("--format", "json")
    row = _poller_row(capsys)
    assert row["lastCycle"]["scopesPolled"] == 12
    assert [s["scope"] for s in row["lastCycle"]["scopesFailed"]] == ["octo/repo-m"]
    assert row["lastCycle"]["scopesFailed"][0]["permanent"] is True
    assert [s["scope"] for s in row["lastCycle"]["scopesSkipped"]] == ["octo/repo-z"]
