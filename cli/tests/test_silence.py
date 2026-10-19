"""The silent-session watchdog (issue-340, part 2).

`session.silent` is emitted once for an active, progress-labelled session that has
produced no event of any kind for `progress.silenceSeconds` — read from the event log,
inside a daemon that already exists.

Spec: docs/specs/issue-340/testing-plan.md (T11).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from the_loop import eventlog
from the_loop.channels import bus as channel_bus
from the_loop.channels.base import PostResult
from the_loop.core import progress as core_progress
from the_loop.core import sessions as core_sessions
from the_loop.core import silence

REF = "github:octo/repo#340"
OTHER = "github:octo/repo#341"
NOW = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
SILENCE = 1800


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _ts(ago_seconds: int) -> str:
    return _stamp(NOW - timedelta(seconds=ago_seconds))


def _config(tmp_path, silence_seconds=SILENCE, **extra):
    config = {
        "state": {"root": str(tmp_path / ".the-loop")},
        "progress": {"silenceSeconds": silence_seconds},
    }
    config.update(extra)
    return config


CLOCK = {"now": NOW}


@pytest.fixture
def log(tmp_path, monkeypatch):
    """A real event log whose clock the test owns, so the watchdog's own record is
    stamped on the same timeline as the `now` each scan is handed."""
    CLOCK["now"] = NOW
    monkeypatch.setattr(eventlog, "_utcnow", lambda: _stamp(CLOCK["now"]))
    path = tmp_path / ".the-loop" / "logs" / "events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("")
    eventlog.configure("silence", path=path)
    yield path
    eventlog.reset()


def _write(path, event, ago, work_item=REF, **fields):
    row = {"ts": _ts(ago), "event": event, "work_item": work_item, **fields}
    with open(path, "a") as handle:
        handle.write(json.dumps(row) + "\n")


@pytest.fixture
def world(monkeypatch):
    """Registered sessions, the labels each work item carries, and what was published."""
    state = {
        "sessions": [{"ref": REF, "createdAt": _ts(7200)}],
        "labels": {REF: ["the-loop: progress"], OTHER: ["the-loop: progress"]},
        "label_reads": [],
        "status_asked": [],
        "published": [],
    }

    def fake_list(status=None, config=None, **_):
        state["status_asked"].append(status)
        return list(state["sessions"])

    def fake_labels(ref, config):
        state["label_reads"].append(ref.ref)
        value = state["labels"][ref.ref]
        if isinstance(value, Exception):
            raise value
        return list(value)

    def fake_publish(event, cli_config=None, **kwargs):
        state["published"].append((event, kwargs))
        return channel_bus.PublishResult(
            record=None, posts=[PostResult(channel="slack", ok=True)]
        )

    monkeypatch.setattr(core_sessions, "list_sessions", fake_list)
    monkeypatch.setattr(core_progress, "_labels_of", fake_labels)
    monkeypatch.setattr(channel_bus, "publish", fake_publish)
    return state


def _silent_events(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [r for r in rows if r["event"] == "session.silent"]


def test_a_labelled_session_quiet_past_the_threshold_gets_one_silent_event(
    tmp_path, log, world
):
    """
    Feature: a stuck session stops looking like hard work
      Scenario: no event for longer than progress.silenceSeconds
        Given an active session of a progress-labelled work item
        And its newest event is older than the threshold
        When the watchdog scans
        Then one session.silent event is published and logged, and the item is named
    """
    _write(log, "session.progress", ago=SILENCE + 600)
    assert silence.scan(_config(tmp_path), now=NOW, log_path=log) == [REF]
    ((event, kwargs),) = world["published"]
    assert event.event_type == "session.silent" and event.work_item == REF
    assert "stuck" in event.text and kwargs["record"] is False
    (row,) = _silent_events(log)
    assert row["work_item"] == REF and row["level"] == "warning"
    assert row["silent_seconds"] >= SILENCE


def test_a_session_with_recent_activity_is_left_alone_and_costs_no_tracker_call(
    tmp_path, log, world
):
    _write(log, "comment.agent", ago=60)
    assert silence.scan(_config(tmp_path), now=NOW, log_path=log) == []
    assert world["published"] == [] and world["label_reads"] == []


def test_it_does_not_repeat_until_the_session_does_something(tmp_path, log, world):
    """
    Scenario: said once per silence
      Given the watchdog already reported this silence
      When it scans again, and the publish itself left bus and channel records
      Then it stays quiet; after new activity and a new silence it speaks again
    """
    config = _config(tmp_path)
    _write(log, "session.progress", ago=SILENCE + 600)
    assert silence.scan(config, now=NOW, log_path=log) == [REF]
    # What every publish leaves behind must not read as the session being alive.
    _write(log, "bus.recorded", ago=-5)  # stamped AFTER the silent event, as they are
    _write(log, "channel.posted", ago=-6)
    later = NOW + timedelta(seconds=SILENCE * 3)
    CLOCK["now"] = later
    assert silence.scan(config, now=later, log_path=log) == []
    # The session does something; later it goes quiet again.
    CLOCK["now"] = later + timedelta(seconds=10)
    eventlog.emit("session.progress", work_item=REF)
    later2 = later + timedelta(seconds=SILENCE + 60)
    CLOCK["now"] = later2
    assert silence.scan(config, now=later2, log_path=log) == [REF]
    assert len(_silent_events(log)) == 2


def test_an_unlabelled_work_item_is_never_reported(tmp_path, log, world):
    world["labels"][REF] = ["bug"]
    _write(log, "session.progress", ago=SILENCE + 600)
    assert silence.scan(_config(tmp_path), now=NOW, log_path=log) == []
    assert world["published"] == []
    assert world["label_reads"] == [REF]  # read only because it was past the threshold


def test_only_active_sessions_are_considered(tmp_path, log, world):
    _write(log, "session.progress", ago=SILENCE + 600)
    silence.scan(_config(tmp_path), now=NOW, log_path=log)
    assert world["status_asked"] == ["active"]


def test_a_session_with_no_events_ages_from_when_it_was_created(tmp_path, log, world):
    world["sessions"] = [{"ref": REF, "createdAt": _ts(SILENCE + 5)}]
    assert silence.scan(_config(tmp_path), now=NOW, log_path=log) == [REF]
    world["sessions"] = [{"ref": REF, "createdAt": _ts(60)}]
    world["published"].clear()
    assert silence.scan(_config(tmp_path), now=NOW, log_path=log) == []


def test_other_work_items_events_do_not_count_as_this_ones(tmp_path, log, world):
    world["sessions"] = [{"ref": REF, "createdAt": _ts(7200)}]
    _write(log, "session.progress", ago=10, work_item=OTHER)
    assert silence.scan(_config(tmp_path), now=NOW, log_path=log) == [REF]


def test_a_fault_on_one_item_does_not_stop_the_rest(tmp_path, log, world):
    world["sessions"] = [
        {"ref": REF, "createdAt": _ts(7200)},
        {"ref": OTHER, "createdAt": _ts(7200)},
    ]
    world["labels"][REF] = RuntimeError("tracker down")
    assert silence.scan(_config(tmp_path), now=NOW, log_path=log) == [OTHER]


def test_it_is_off_unless_the_threshold_is_set(tmp_path, log, world):
    _write(log, "session.progress", ago=99999)
    assert (
        silence.scan(_config(tmp_path, silence_seconds=0), now=NOW, log_path=log) == []
    )
    assert world["status_asked"] == []  # not even the registry was read
    off = _config(tmp_path, silence_seconds=SILENCE)
    off["progress"]["label"] = ""
    assert silence.scan(off, now=NOW, log_path=log) == []


# -- the watcher -------------------------------------------------------------------


def test_the_watcher_is_none_when_off_or_when_the_log_it_reads_is_off(tmp_path):
    stop = threading.Event()
    assert silence.start_watcher({}, stop) is None
    assert silence.start_watcher(_config(tmp_path, silence_seconds=0), stop) is None
    no_log = _config(tmp_path, eventLog={"enabled": False})
    assert silence.start_watcher(no_log, stop) is None


def test_the_watcher_scans_until_its_daemon_stops_it(tmp_path, monkeypatch):
    seen = threading.Event()
    calls = []

    def fake_scan(config, **_):
        calls.append(config)
        seen.set()
        raise RuntimeError("a failing scan must not kill the thread")

    monkeypatch.setattr(silence, "scan", fake_scan)
    monkeypatch.setattr(silence, "watch_interval", lambda _s: 0.01)
    stop = threading.Event()
    thread = silence.start_watcher(_config(tmp_path), stop)
    assert thread is not None and thread.daemon
    assert seen.wait(2)
    stop.set()
    thread.join(2)
    assert not thread.is_alive() and calls


def test_the_scan_interval_is_a_quarter_of_the_threshold_within_bounds():
    assert silence.watch_interval(1800) == 300  # capped at five minutes
    assert silence.watch_interval(400) == 100
    assert silence.watch_interval(60) == 30  # floored at thirty seconds
