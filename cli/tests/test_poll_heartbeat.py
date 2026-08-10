"""The poller's heartbeat — write, read, and never break ingress (issue-191, T1).

The heartbeat is what `the-loop poll status` reports *beyond* liveness: when this
poller started, when it last finished a cycle, and what that cycle did. Two
properties matter more than the round-trip. It must be **atomic**, because it is
rewritten on every cycle and read by a command that can run at any moment; and a
write failure must **warn once and be swallowed**, because observability that
stops the poller delivering events is worse than no observability.

Spec: docs/specs/issue-191/design.md; testing plan row T1.
"""

import json
from types import SimpleNamespace

from the_loop.poller.heartbeat import Heartbeat, PollHeartbeat


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
    PollHeartbeat(path, pid=4242, interval_seconds=90).record(_summary())

    beat = PollHeartbeat.read(path)
    assert beat is not None
    assert beat.pid == 4242
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
    PollHeartbeat(path, pid=7).record(None)

    beat = PollHeartbeat.read(path)
    assert beat is not None
    assert beat.started_at != ""
    assert beat.last_cycle_at == ""
    assert beat.last_cycle == {}


def test_started_at_is_stable_across_cycles(tmp_path):
    """The start time is the poller's, so it must not move on every cycle."""
    path = tmp_path / "poll-status.json"
    writer = PollHeartbeat(path, pid=7, started_at="2026-08-10T09:00:00Z")
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
        pid=0, started_at="", last_cycle_at="", interval_seconds=0, last_cycle={}
    )
