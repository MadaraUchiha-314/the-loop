"""Unit tests for the core facade's event-log query surface (issue-161, T1)."""

import json

import pytest

from the_loop.core import events


def _write_log(path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def test_query_events_filters_and_limits(tmp_path):
    log = tmp_path / "events.jsonl"
    _write_log(
        log,
        [
            {
                "ts": "2026-08-05T01:00:00Z",
                "event": "dispatch.spawned",
                "level": "info",
            },
            {
                "ts": "2026-08-05T02:00:00Z",
                "event": "dispatch.failed",
                "level": "error",
            },
            {"ts": "2026-08-05T03:00:00Z", "event": "session.closed", "level": "info"},
        ],
    )
    all_events = events.query_events(str(log), limit=0)
    assert len(all_events) == 3

    errors = events.query_events(str(log), min_level="error", limit=0)
    assert [e["event"] for e in errors] == ["dispatch.failed"]

    last_one = events.query_events(str(log), limit=1)
    assert [e["event"] for e in last_one] == ["session.closed"]


def test_query_events_negative_limit_is_value_error(tmp_path):
    with pytest.raises(ValueError):
        events.query_events(str(tmp_path / "events.jsonl"), limit=-1)


def test_event_types_catalog_is_a_copy():
    catalog = events.event_types()
    assert catalog
    catalog.clear()
    assert events.event_types()
