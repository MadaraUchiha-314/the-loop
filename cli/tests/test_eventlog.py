"""Unit tests for the structured event log and the `events` command (issue-50)."""

import json
import re
from pathlib import Path

from the_loop import eventlog
from the_loop.cli import main
from the_loop.commands import iter_commands
from the_loop.commands.events import parse_since


# -- writer ---------------------------------------------------------------------


def test_emit_writes_one_json_line_with_envelope(tmp_path):
    log = eventlog.EventLog(tmp_path / "events.jsonl", source="gh-webhook")
    log.emit("webhook.received", gh_event="issues", delivery_id="d-1", verified=True)
    (line,) = (tmp_path / "events.jsonl").read_text().splitlines()
    record = json.loads(line)
    assert record["source"] == "gh-webhook"
    assert record["event"] == "webhook.received"
    assert record["level"] == "info"
    assert record["gh_event"] == "issues"
    assert record["delivery_id"] == "d-1"
    assert record["verified"] is True
    assert isinstance(record["pid"], int)
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", record["ts"])


def test_emit_drops_none_fields_and_normalizes_level(tmp_path):
    log = eventlog.EventLog(tmp_path / "e.jsonl", source="poll")
    log.emit("poll.cycle", level="nonsense", errors=None, items_seen=0)
    record = json.loads((tmp_path / "e.jsonl").read_text())
    assert "errors" not in record
    assert record["level"] == "info"


def test_disabled_log_writes_nothing(tmp_path):
    log = eventlog.EventLog(tmp_path / "e.jsonl", source="poll", enabled=False)
    log.emit("poll.cycle")
    assert not (tmp_path / "e.jsonl").exists()


def test_module_emit_is_noop_until_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    eventlog.emit("webhook.received")  # must not raise or create files
    assert not Path(eventlog.DEFAULT_PATH).exists()
    eventlog.configure("gh-webhook", path=tmp_path / "e.jsonl")
    eventlog.emit("webhook.received", delivery_id="d-1")
    assert (tmp_path / "e.jsonl").is_file()


def test_write_failure_is_swallowed(tmp_path):
    target = tmp_path / "a-directory"
    target.mkdir()
    log = eventlog.EventLog(target, source="sessions")  # opening a dir fails
    log.emit("session.closed", work_item="github:octo/repo#1")  # must not raise
    log.emit("session.closed", work_item="github:octo/repo#1")  # warned once


# -- reader ---------------------------------------------------------------------


def _write_log(path, records):
    with open(path, "w") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


SAMPLE = [
    {
        "ts": "2026-07-22T10:00:00.000Z",
        "source": "gh-webhook",
        "event": "webhook.received",
        "level": "info",
        "delivery_id": "d-1",
    },
    {
        "ts": "2026-07-22T10:00:01.000Z",
        "source": "gh-webhook",
        "event": "routing.routed",
        "level": "info",
        "delivery_id": "d-1",
        "work_items": ["github:octo/repo#15"],
    },
    {
        "ts": "2026-07-22T10:00:02.000Z",
        "source": "gh-webhook",
        "event": "dispatch.failed",
        "level": "error",
        "delivery_id": "d-1",
        "work_item": "github:octo/repo#15",
        "will_retry": True,
    },
    {
        "ts": "2026-07-22T11:00:00.000Z",
        "source": "poll",
        "event": "poll.cycle",
        "level": "info",
        "items_seen": 2,
    },
]


def test_read_events_filters(tmp_path):
    path = tmp_path / "events.jsonl"
    _write_log(path, SAMPLE)
    assert len(list(eventlog.read_events(path))) == 4
    assert [r["event"] for r in eventlog.read_events(path, types=["dispatch.*"])] == [
        "dispatch.failed"
    ]
    # work_item matches both the scalar field and the work_items list
    assert len(list(eventlog.read_events(path, work_item="github:octo/repo#15"))) == 2
    assert len(list(eventlog.read_events(path, delivery_id="d-1"))) == 3
    assert [r["event"] for r in eventlog.read_events(path, source="poll")] == [
        "poll.cycle"
    ]
    assert [r["event"] for r in eventlog.read_events(path, min_level="error")] == [
        "dispatch.failed"
    ]
    assert [
        r["event"] for r in eventlog.read_events(path, since="2026-07-22T10:30:00.000Z")
    ] == ["poll.cycle"]


def test_read_events_tolerates_missing_file_and_corrupt_lines(tmp_path):
    assert list(eventlog.read_events(tmp_path / "nope.jsonl")) == []
    path = tmp_path / "events.jsonl"
    path.write_text(
        json.dumps(SAMPLE[0])
        + "\n"
        + "{not json\n"
        + '"a bare string"\n'
        + json.dumps(SAMPLE[3])[: len(json.dumps(SAMPLE[3])) // 2]  # torn write
        + "\n"
        + json.dumps(SAMPLE[3])
        + "\n"
    )
    events = [r["event"] for r in eventlog.read_events(path)]
    assert events == ["webhook.received", "poll.cycle"]


def test_every_emitted_event_type_is_documented():
    """Instrumentation and the EVENT_TYPES catalog must not drift apart —
    the catalog is what `the-loop events --types` and agents rely on."""
    package = Path(eventlog.__file__).parent
    emitted = set()
    for source in package.rglob("*.py"):
        emitted.update(
            re.findall(r'\bemit\(\s*"([a-z0-9_.]+)"', source.read_text(), re.S)
        )
    assert emitted, "expected instrumentation emit() calls in the package"
    undocumented = emitted - set(eventlog.EVENT_TYPES)
    assert not undocumented, f"emitted but not in EVENT_TYPES: {sorted(undocumented)}"


# -- `the-loop events` command ---------------------------------------------------


def test_events_is_registered():
    assert "events" in {c.name for c in iter_commands()}


def test_events_types_lists_catalog(capsys):
    assert main(["events", "--types"]) == 0
    out = capsys.readouterr().out
    for name in eventlog.EVENT_TYPES:
        assert name in out


def test_events_table_and_filters(tmp_path, capsys):
    path = tmp_path / "events.jsonl"
    _write_log(path, SAMPLE)
    assert main(["events", "--file", str(path), "--level", "error"]) == 0
    out = capsys.readouterr().out
    assert "dispatch.failed" in out
    assert "webhook.received" not in out
    assert "will_retry=True" in out  # non-envelope fields land in the detail column


def test_events_json_formats(tmp_path, capsys):
    path = tmp_path / "events.jsonl"
    _write_log(path, SAMPLE)
    assert main(["events", "--file", str(path), "--format", "json"]) == 0
    records = json.loads(capsys.readouterr().out)
    assert [r["event"] for r in records] == [
        "webhook.received",
        "routing.routed",
        "dispatch.failed",
        "poll.cycle",
    ]
    assert (
        main(["events", "--file", str(path), "--format", "jsonl", "--limit", "2"]) == 0
    )
    lines = capsys.readouterr().out.strip().splitlines()
    assert [json.loads(line)["event"] for line in lines] == [
        "dispatch.failed",
        "poll.cycle",
    ]


def test_events_missing_file_is_empty_not_an_error(tmp_path, capsys):
    assert main(["events", "--file", str(tmp_path / "nope.jsonl")]) == 0
    assert "(no matching events)" in capsys.readouterr().err


def test_parse_since_relative_and_iso():
    assert parse_since("2026-07-22T10:00:00Z") == "2026-07-22T10:00:00Z"
    assert re.match(r"^\d{4}-\d{2}-\d{2}T", parse_since("15m"))
    assert parse_since("2h") < parse_since("15m")  # 2h ago is earlier
