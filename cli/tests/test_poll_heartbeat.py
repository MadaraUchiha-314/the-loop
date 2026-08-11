"""The poller's heartbeat — write, read, and never break ingress (issue-191, T1;
issue-205, T1-T3).

The heartbeat is what `the-loop poll status` reports *beyond* liveness: when this
poller started, when it last finished a cycle, and what that cycle did. Two
properties matter more than the round-trip. It must be **atomic**, because it is
rewritten on every cycle and read by a command that can run at any moment; and a
write failure must **warn once and be swallowed**, because observability that
stops the poller delivering events is worse than no observability.

It carries **no pid** (issue-205): naming the process is the lock's job, and the
last test here is why the two cannot be one file — the atomicity above is exactly
what would free the lock.

Spec: docs/specs/issue-191/design.md; docs/specs/issue-205/requirements.md.
"""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from the_loop.poller.heartbeat import Heartbeat, PollHeartbeat
from the_loop.runlock import RunLock


def _summary(**overrides):
    """A stand-in for PollSummary — read duck-typed by the writer."""
    fields = {
        "items_seen": 5,
        "spawns": 1,
        "comments_forwarded": 2,
        "closures": 0,
        "failures": 0,
        "errors": [],
        "interrupted": False,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_record_then_read_round_trips(tmp_path):
    path = tmp_path / "poll-status.json"
    PollHeartbeat(path, interval_seconds=90).record(_summary())

    beat = PollHeartbeat.read(path)
    assert beat is not None
    assert beat.interval_seconds == 90
    assert beat.started_at and beat.last_cycle_at
    assert beat.last_cycle == {
        "itemsSeen": 5,
        "spawns": 1,
        "commentsForwarded": 2,
        "closures": 0,
        "failures": 0,
        "errors": 0,
        "interrupted": False,
    }


def test_a_started_poller_records_no_cycle(tmp_path):
    """`record(None)` is "up, nothing polled yet" — not "never ran"."""
    path = tmp_path / "poll-status.json"
    PollHeartbeat(path).record(None)

    beat = PollHeartbeat.read(path)
    assert beat is not None
    assert beat.started_at != ""
    assert beat.last_cycle_at == ""
    assert beat.last_cycle == {}


def test_started_at_is_stable_across_cycles(tmp_path):
    """The start time is the poller's, so it must not move on every cycle."""
    path = tmp_path / "poll-status.json"
    writer = PollHeartbeat(path, started_at="2026-08-10T09:00:00Z")
    writer.record(_summary())
    first = PollHeartbeat.read(path)
    writer.record(_summary(items_seen=9))
    second = PollHeartbeat.read(path)

    assert first is not None and second is not None
    assert first.started_at == second.started_at == "2026-08-10T09:00:00Z"
    assert second.last_cycle["itemsSeen"] == 9


def test_errors_are_counted_and_interruption_is_carried(tmp_path):
    path = tmp_path / "poll-status.json"
    PollHeartbeat(path).record(_summary(errors=["boom", "bang"], interrupted=True))

    beat = PollHeartbeat.read(path)
    assert beat is not None
    assert beat.last_cycle["errors"] == 2
    assert beat.last_cycle["interrupted"] is True


def test_write_is_atomic_and_leaves_no_temporary_behind(tmp_path):
    path = tmp_path / "poll-status.json"
    writer = PollHeartbeat(path)
    writer.record(_summary())
    writer.record(_summary())

    assert json.loads(path.read_text())["lastCycle"]["itemsSeen"] == 5
    assert [p.name for p in tmp_path.iterdir()] == ["poll-status.json"]


def test_a_missing_or_unreadable_heartbeat_reads_as_none(tmp_path):
    assert PollHeartbeat.read(tmp_path / "absent.json") is None

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json")
    assert PollHeartbeat.read(corrupt) is None

    wrong_shape = tmp_path / "list.json"
    wrong_shape.write_text("[1, 2, 3]")
    assert PollHeartbeat.read(wrong_shape) is None


def test_an_unwritable_path_warns_once_and_never_raises(tmp_path, caplog):
    """A health file that cannot be written must not stop the poller."""
    # A file where a directory is needed: every write below fails at mkdir.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    writer = PollHeartbeat(blocker / "poll-status.json")

    with caplog.at_level("WARNING"):
        writer.record(_summary())
        writer.record(_summary())

    warnings = [r for r in caplog.records if "poll heartbeat" in r.getMessage()]
    assert len(warnings) == 1, "warned once, not on every cycle"


def test_the_dataclass_survives_an_empty_document(tmp_path):
    """A truncated or hand-edited file degrades to defaults, not an exception."""
    path = tmp_path / "poll-status.json"
    path.write_text("{}")

    beat = PollHeartbeat.read(path)
    assert beat == Heartbeat(
        started_at="", last_cycle_at="", interval_seconds=0, last_cycle={}
    )


# -- one source of truth for the pid (issue-205) ---------------------------------


def test_the_heartbeat_records_no_pid(tmp_path):
    """T1: the process is the lock's to name, so this file does not name it.

    Asserted on the document *and* the model: a `pid` key nothing reads is still
    a second answer to a question `poll.pid` already owns, and an attribute
    nothing reads is how it would come back.
    """
    path = tmp_path / "poll-status.json"
    PollHeartbeat(path, interval_seconds=60).record(_summary())

    document = json.loads(path.read_text())
    assert "pid" not in document
    assert set(document) == {"startedAt", "lastCycleAt", "intervalSeconds", "lastCycle"}
    assert not hasattr(Heartbeat(), "pid")


def test_an_older_heartbeat_carrying_a_pid_still_reads(tmp_path):
    """T3: an upgrade meets a file the previous version wrote; the pid is dropped."""
    path = tmp_path / "poll-status.json"
    path.write_text(
        json.dumps(
            {
                "pid": 4242,
                "startedAt": "2026-08-10T09:00:00Z",
                "lastCycleAt": "2026-08-10T09:01:00Z",
                "intervalSeconds": 60,
                "lastCycle": {"itemsSeen": 3},
            }
        )
    )

    beat = PollHeartbeat.read(path)
    assert beat is not None
    assert beat.started_at == "2026-08-10T09:00:00Z"
    assert beat.last_cycle["itemsSeen"] == 3
    assert not hasattr(beat, "pid")


def test_writing_a_heartbeat_over_the_pidfile_would_free_the_lock(tmp_path):
    """T2: the measurement behind "these cannot be one file" (decision-076).

    The atomic rewrite two tests up is exactly what makes merging them unsafe:
    `os.replace` puts a **new inode** at the path, and the flock is held on the
    old one. So the poller would keep a lock on an orphan while the path it
    guards went free — and the next `poll start` would take it and run a second
    poller against the same ledger, which is the defect `RunLock` exists to
    prevent (issue-159).
    """
    pidfile = tmp_path / "poll.pid"
    lock = RunLock(pidfile, name="poller")
    assert lock.acquire()
    try:
        assert RunLock(pidfile, name="probe").is_held(), "held before the rewrite"

        # Precisely what PollHeartbeat._write does, aimed at the pidfile.
        handle = tempfile.NamedTemporaryFile("w", dir=str(tmp_path), delete=False)
        with handle:
            handle.write("{}")
        Path(handle.name).replace(pidfile)

        assert not RunLock(pidfile, name="probe").is_held(), (
            "an atomic rewrite frees the lock — which is why the heartbeat is a "
            "second file, not a section of the pidfile"
        )
    finally:
        lock.release()
