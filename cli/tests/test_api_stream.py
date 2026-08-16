"""Resolution of the `service.stream` block, and the stream's own primitives (issue-239).

The block governs `GET /api/v1/stream` — a **read** surface over the same records
`GET /api/v1/events` serves, held open. Three knobs and no more: everything else the
stream needs is a constant an operator would have no basis to choose, and lives in
:mod:`the_loop.api.stream`.

These are the unit-level tests (testing-plan T1). The connection itself is exercised in
``test_stream_integration.py``.
"""

import asyncio
import builtins
import json

import pytest

from the_loop.api import stream
from the_loop.api.config import DEFAULT_STREAM_MAX_SUBSCRIBERS, stream_config


# -- service.stream resolution (task 1) -----------------------------------------


def test_defaults_serve_the_stream_with_a_bounded_subscriber_count():
    """
    Feature: the stream is on by default and bounded by default
      Scenario: no service.stream block is configured
        Given a CLI config with no stream block
        When the stream config resolves
        Then the stream is enabled, capped at the default subscriber count,
             and keeps connections alive on the default interval

    Requirement: docs/specs/issue-239/requirements.md R1.4, R5.2
    """
    conf = stream_config({})
    assert conf["enabled"] is True
    assert conf["maxSubscribers"] == DEFAULT_STREAM_MAX_SUBSCRIBERS
    assert conf["keepAliveSeconds"] == 15


def test_an_absent_block_is_the_defaults_not_the_off_switch():
    """A missing section means "unconfigured", never "disabled" — `enabled: false` is
    the off switch, and it has to be written."""
    assert stream_config(None)["enabled"] is True
    assert stream_config({"service": {}})["enabled"] is True


def test_enabled_false_is_the_off_switch():
    """
    Feature: a deployment can narrow itself to REST-only
      Scenario: the operator disables the stream
        Given service.stream.enabled is false
        When the stream config resolves
        Then the stream is disabled

    Requirement: docs/specs/issue-239/requirements.md R1.1
    """
    conf = stream_config({"service": {"stream": {"enabled": False}}})
    assert conf["enabled"] is False


def test_configured_values_win_key_by_key():
    conf = stream_config(
        {"service": {"stream": {"maxSubscribers": 3, "keepAliveSeconds": 45}}}
    )
    assert conf["maxSubscribers"] == 3
    assert conf["keepAliveSeconds"] == 45
    assert conf["enabled"] is True


@pytest.mark.parametrize("value", [0, -1, "nonsense", None])
def test_a_nonsense_subscriber_cap_clamps_up_rather_than_disabling_the_bound(value):
    """
    Feature: the subscriber bound cannot be configured away
      Scenario: maxSubscribers is zero, negative or unparseable
        Given a hand-edited service.stream.maxSubscribers
        When the stream config resolves
        Then the cap is at least one — never zero, never unbounded

    Requirement: docs/specs/issue-239/requirements.md R5.2 (abuse case 1)

    A cap of 0 would refuse every connection, and a cap that fell through to
    "unlimited" would be abuse case 1 handed a configuration switch. Both
    directions resolve to a usable, bounded number.
    """
    conf = stream_config({"service": {"stream": {"maxSubscribers": value}}})
    assert conf["maxSubscribers"] >= 1


def test_the_schema_refuses_an_unknown_key_under_stream():
    """
    Feature: a mistyped stream key is refused, not ignored
      Scenario: the operator writes an option that does not exist
        Given a CLI config with service.stream.maxSubscriber (singular)
        When it is validated against the packaged schema
        Then validation fails naming the key

    Requirement: docs/specs/issue-239/requirements.md R5.2

    `additionalProperties: false` is what makes a typo a loud failure instead of a
    silently-ignored bound.
    """
    from the_loop import configschema

    errors = configschema.validate({"service": {"stream": {"maxSubscriber": 4}}})
    assert any("maxSubscriber" in e for e in errors), (
        f"an unknown stream key must be named in the errors, got {errors}"
    )
    assert configschema.validate({"service": {"stream": {"maxSubscribers": 4}}}) == []


# -- the log tailer and the cursor (task 2) -------------------------------------


def _write(path, *records):
    """Append whole JSONL records, the way `eventlog.EventLog.emit` does."""
    with open(path, "a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")


def test_a_tail_starting_at_the_end_sees_only_what_arrives_after_it(tmp_path):
    """
    Feature: a subscriber joins a running system
      Scenario: the log already holds history when a client connects
        Given an event log with records already in it
        When a tail is opened at the end and a new record is appended
        Then only the new record is read

    Requirement: docs/specs/issue-239/requirements.md R1.2
    """
    log = tmp_path / "events.jsonl"
    _write(log, {"event": "session.spawned", "work_item": "github:o/r#1"})

    tail = stream.LogTail(log)
    tail.seek_to_end()
    assert list(tail.read()) == []

    _write(log, {"event": "graph.advanced", "work_item": "github:o/r#1"})
    (record,) = list(tail.read())
    assert record.data["event"] == "graph.advanced"


def test_a_partial_trailing_line_is_buffered_until_it_is_whole(tmp_path):
    """
    Feature: a tail never reads half a record
      Scenario: the tailer reads while another process is mid-write
        Given a log whose last line has no newline yet
        When the tail reads, and the rest of the line arrives
        Then nothing is emitted on the first read and the whole record on the second

    Requirement: docs/specs/issue-239/requirements.md R1.2

    Several processes append to this file (poller, receiver, harness, service).
    Emitting a truncated line would put malformed JSON on the wire, and skipping
    it would lose the record entirely once it completed.
    """
    log = tmp_path / "events.jsonl"
    log.write_text('{"event":"graph.adv')

    tail = stream.LogTail(log)
    assert list(tail.read()) == []

    with open(log, "a", encoding="utf-8") as handle:
        handle.write('anced","work_item":"github:o/r#1"}\n')

    (record,) = list(tail.read())
    assert record.data["event"] == "graph.advanced"


def test_the_cursor_is_the_offset_after_the_record(tmp_path):
    """Replaying from a record's cursor must yield the records after it, not it again."""
    log = tmp_path / "events.jsonl"
    _write(log, {"event": "a"}, {"event": "b"})

    first, second = list(stream.LogTail(log).read())
    assert first.cursor < second.cursor
    assert second.cursor == log.stat().st_size

    resumed = stream.LogTail(log, offset=first.cursor)
    assert [r.data["event"] for r in resumed.read()] == ["b"]


def test_the_control_planes_own_api_requests_never_reach_the_stream(tmp_path):
    """
    Feature: the stream cannot feed itself
      Scenario: the control plane refreshes, which emits api.request
        Given a log holding api.request and mcp.call beside a real event
        When the tail reads
        Then only the real event is emitted

    Requirement: docs/specs/issue-239/design.md §Trade-offs

    Every route emits `api.request`. If the stream carried it, a refresh would
    produce API requests -> api.request events -> frames -> another refresh, and
    the loop would never idle. Excluded at the TAILER so no caller can route
    around it, and with no opt-in flag: `GET /api/v1/events` still serves them.
    """
    log = tmp_path / "events.jsonl"
    _write(
        log,
        {"event": "api.request", "path": "/api/v1/work-items"},
        {"event": "graph.advanced", "work_item": "github:o/r#1"},
        {"event": "mcp.call", "tool": "listWorkItems"},
        {"event": "api.request", "path": "/api/v1/sessions"},
    )
    assert [r.data["event"] for r in stream.LogTail(log).read()] == ["graph.advanced"]


def test_an_excluded_record_still_advances_the_cursor(tmp_path):
    """A skipped record must not be re-read forever: the offset moves past it."""
    log = tmp_path / "events.jsonl"
    _write(log, {"event": "api.request"}, {"event": "graph.advanced"})

    tail = stream.LogTail(log)
    list(tail.read())
    assert tail.offset == log.stat().st_size


def test_a_corrupt_line_is_skipped_rather_than_stopping_the_tail(tmp_path):
    """The reader in `eventlog` tolerates corrupt lines; so must this one."""
    log = tmp_path / "events.jsonl"
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    _write(log, {"event": "graph.advanced"})
    assert [r.data["event"] for r in stream.LogTail(log).read()] == ["graph.advanced"]


def test_a_missing_log_reads_as_empty_and_starts_when_it_appears(tmp_path):
    """A workstation that has emitted nothing yet has no file; that is not an error."""
    log = tmp_path / "events.jsonl"
    tail = stream.LogTail(log)
    assert list(tail.read()) == []
    _write(log, {"event": "graph.advanced"})
    assert [r.data["event"] for r in tail.read()] == ["graph.advanced"]


class TestResolveCursor:
    """Where a reconnecting subscriber resumes from — or why it cannot (R1.5)."""

    def test_a_cursor_inside_the_replay_window_replays_from_there(self):
        start, desync = stream.resolve_cursor(1000, size=1200)
        assert (start, desync) == (1000, "")

    def test_no_cursor_starts_at_the_end(self):
        """A first connection wants what happens next, not the whole history."""
        start, desync = stream.resolve_cursor(None, size=1200)
        assert (start, desync) == (1200, "")

    def test_a_cursor_beyond_the_file_means_it_was_truncated(self):
        """
        Feature: a rotated or truncated log is reported, never guessed at
          Scenario: the client's offset is past the end of the file
            Given a cursor of 5000 and a log of 1200 bytes
            When the cursor resolves
            Then the client is told to resynchronise and resumes at the end

        Requirement: docs/specs/issue-239/requirements.md R1.5
        """
        start, desync = stream.resolve_cursor(5000, size=1200)
        assert start == 1200
        assert desync == "truncated"

    def test_a_gap_wider_than_the_replay_window_is_bounded(self):
        """
        Feature: replay cannot be used to read unbounded history
          Scenario: a client asks to resume from far behind
            Given a cursor 4 MiB behind the end of the log
            When the cursor resolves
            Then replay is refused, the client is told, and it resumes at the end

        Requirement: docs/specs/issue-239/requirements.md R1.5 (abuse case 4)
        """
        size = stream.REPLAY_BYTES * 16
        start, desync = stream.resolve_cursor(0, size=size)
        assert start == size
        assert desync == "replay-window"

    def test_a_negative_or_unparseable_cursor_is_a_caller_error(self):
        """Refused, never silently treated as "from the beginning" (abuse case 3)."""
        for bad in ("-1", "nonsense", "1e5", ""):
            with pytest.raises(ValueError):
                stream.parse_cursor(bad)

    def test_a_well_formed_cursor_parses(self):
        assert stream.parse_cursor("148213") == 148213
        assert stream.parse_cursor(None) is None


def test_the_cursor_is_exact_across_a_partial_line_and_non_ascii(tmp_path):
    """
    Feature: a resumed cursor lands on a record boundary
      Scenario: the tail read mid-write, and the log holds non-ASCII text
        Given a log whose records contain multi-byte characters
        And a read that lands in the middle of the last record
        When the record completes and the tail reads again
        Then every cursor equals the file offset just after that record

    Requirement: docs/specs/issue-239/requirements.md R1.5

    The cursor is a BYTE offset the client quotes back as Last-Event-ID, so it has
    to be the offset the filesystem agrees with. Measuring decoded text instead of
    bytes drifts by exactly the number of non-ASCII characters read so far — an
    error invisible on an ASCII fixture and present in every real transcript.
    """
    log = tmp_path / "events.jsonl"
    first = json.dumps({"event": "a", "note": "café ☕"}, separators=(",", ":")) + "\n"
    second = (
        json.dumps({"event": "b", "note": "naïve — ok"}, separators=(",", ":")) + "\n"
    )
    raw = (first + second).encode("utf-8")

    # Land the first read inside the second record, after its first byte.
    cut = len(first.encode("utf-8")) + 1
    log.write_bytes(raw[:cut])

    tail = stream.LogTail(log)
    (record_a,) = list(tail.read())
    assert record_a.cursor == len(first.encode("utf-8"))

    with open(log, "ab") as handle:
        handle.write(raw[cut:])

    (record_b,) = list(tail.read())
    assert record_b.data["event"] == "b"
    assert record_b.cursor == len(raw) == log.stat().st_size

    # And the cursor is usable: resuming from it yields nothing, from A's yields B.
    assert list(stream.LogTail(log, offset=record_b.cursor).read()) == []
    assert [
        r.data["event"] for r in stream.LogTail(log, offset=record_a.cursor).read()
    ] == ["b"]


# -- the broker: fan-out, capacity, back-pressure (task 3) -----------------------


def _run(coro):
    """Drive one coroutine to completion.

    `asyncio.run` rather than a plugin: the broker needs a running loop only
    because `asyncio.Queue` is bound to one, and adding pytest-asyncio to test
    three methods fails the minimalism ladder (reference/minimalism.md).
    """
    return asyncio.run(coro)


def _drain(subscriber):
    frames = []
    while not subscriber.queue.empty():
        frames.append(subscriber.queue.get_nowait())
    return frames


def test_a_connection_beyond_the_configured_maximum_is_refused(tmp_path):
    """
    Feature: an open dashboard cannot starve the REST surface
      Scenario: more connections are opened than the configuration allows
        Given service.stream.maxSubscribers is 2
        When a third connection is opened
        Then it is refused, and the two already open are untouched

    Requirement: docs/specs/issue-239/requirements.md R5.2 (abuse case 1)

    Refused at REGISTRATION, before any queue, task or file handle exists, so the
    cost of a refused connection is one rejected request.
    """

    async def scenario():
        broker = stream.StreamBroker(tmp_path / "events.jsonl", max_subscribers=2)
        first = broker.subscribe()
        second = broker.subscribe()
        assert broker.at_capacity
        with pytest.raises(RuntimeError) as caught:
            broker.subscribe()
        assert "maxSubscribers" in str(caught.value)
        assert broker.count == 2
        broker.unsubscribe(first)
        assert not broker.at_capacity
        broker.subscribe()  # the freed slot is reusable
        assert broker.count == 2
        return second

    _run(scenario())


def test_one_read_serves_every_subscriber(tmp_path):
    """
    Feature: an idle subscriber costs the service almost nothing
      Scenario: several subscribers are connected when a record is appended
        Given three open subscribers
        When one tick runs
        Then the event log is opened once, not once per subscriber

    Requirement: docs/specs/issue-239/requirements.md R5.3

    The property the shared tailer exists for. Asserted by counting opens rather
    than by inspecting the design, because "one tailer" is easy to write and easy
    to lose to a later refactor that moves the read inside the fan-out loop.
    """
    log = tmp_path / "events.jsonl"

    async def scenario():
        broker = stream.StreamBroker(log, max_subscribers=8)
        subscribers = [broker.subscribe() for _ in range(3)]
        # Appended AFTER subscribing: everything at or below the tail's offset at
        # registration belongs to each connection's own replay, not to the shared
        # tailer, so a record written first would (correctly) produce no frame.
        _write(log, {"event": "graph.advanced", "work_item": "github:o/r#1"})
        opens = 0
        original = builtins.open

        def counting_open(*args, **kwargs):
            nonlocal opens
            opens += 1
            return original(*args, **kwargs)

        builtins.open = counting_open
        try:
            broker.tick()
        finally:
            builtins.open = original

        assert opens == 1, f"the log was opened {opens} times for 3 subscribers"
        for subscriber in subscribers:
            (frame,) = _drain(subscriber)
            assert frame.kind == "log"
            assert frame.data["event"] == "graph.advanced"

    _run(scenario())


def test_a_work_item_filter_excludes_another_items_events(tmp_path):
    """
    Feature: a subscriber sees only what it asked for
      Scenario: two work items are active and a subscriber filters to one
        Given a subscriber filtered to github:o/r#1
        When events for #1 and #2 are appended
        Then only #1's event reaches it, and an unfiltered subscriber sees both

    Requirement: docs/specs/issue-239/requirements.md R1.3
    """
    log = tmp_path / "events.jsonl"

    async def scenario():
        broker = stream.StreamBroker(log, max_subscribers=8)
        filtered = broker.subscribe(work_items=["github:o/r#1"])
        everything = broker.subscribe()
        _write(
            log,
            {"event": "graph.advanced", "work_item": "github:o/r#1"},
            {"event": "graph.advanced", "work_item": "github:o/r#2"},
            {"event": "routing.routed", "work_items": ["github:o/r#1", "github:o/r#9"]},
        )
        broker.tick()

        assert [f.data.get("work_item") for f in _drain(filtered)] == [
            "github:o/r#1",
            None,  # the routing event, matched through `work_items`
        ]
        assert len(_drain(everything)) == 3

    _run(scenario())


def test_a_subscriber_that_stops_reading_is_bounded_and_told_to_resync(tmp_path):
    """
    Feature: a slow client cannot grow the service's memory
      Scenario: a subscriber stops reading while events keep arriving
        Given a subscriber whose queue is full
        When another frame is offered
        Then the queue is drained to a single desync frame and stays that size

    Requirement: docs/specs/issue-239/requirements.md R5.4 (abuse case 5)

    Dropped to a RESYNC rather than disconnected: the connection is still useful,
    and one desync is a smaller, bounded promise than an unbounded backlog. The
    client's response — refetch everything — is the same one a rotated log gets.
    """

    async def scenario():
        broker = stream.StreamBroker(tmp_path / "events.jsonl", max_subscribers=8)
        subscriber = broker.subscribe()
        frame = stream.Frame(kind="log", data={"event": "graph.advanced"}, cursor=1)

        for _ in range(stream.QUEUE_SIZE):
            assert subscriber.offer(frame) is True
        assert subscriber.queue.qsize() == stream.QUEUE_SIZE

        assert subscriber.offer(frame) is False
        assert subscriber.queue.qsize() == 1
        (only,) = _drain(subscriber)
        assert only.kind == "desync"
        assert only.data["reason"] == "queue-overflow"

        # Still bounded while it stays behind: no second desync piles up.
        for _ in range(stream.QUEUE_SIZE * 2):
            subscriber.offer(frame)
        assert subscriber.queue.qsize() <= stream.QUEUE_SIZE

    _run(scenario())


def test_the_transcript_watch_reports_growth_without_carrying_content(tmp_path):
    """
    Feature: the trace panel updates while the agent works
      Scenario: the watched session's transcript grows
        Given a subscriber watching github:o/r#1's transcript
        When the transcript file gains a line
        Then a transcript frame carries the ref and the new line count, and no text

    Requirement: docs/specs/issue-239/requirements.md R2.3

    A line count, not the content: the client then calls
    GET /api/v1/sessions/transcript, which owns the path validation and the
    fail-closed rules (issue-209). Streaming content would duplicate that boundary.
    """
    transcript = tmp_path / "session.jsonl"
    transcript.write_text('{"type":"user"}\n')

    async def scenario():
        broker = stream.StreamBroker(
            tmp_path / "events.jsonl",
            max_subscribers=8,
            transcript_path=lambda ref: transcript,
        )
        subscriber = broker.subscribe(transcripts=["github:o/r#1"])

        broker.tick()  # first sighting establishes the baseline, emits nothing
        assert _drain(subscriber) == []

        with open(transcript, "a", encoding="utf-8") as handle:
            handle.write('{"type":"assistant"}\n')
        broker.tick()

        (frame,) = _drain(subscriber)
        assert frame.kind == "transcript"
        assert frame.data == {"ref": "github:o/r#1", "totalLines": 2}

    _run(scenario())


def test_an_unresolvable_transcript_is_a_normal_state_not_a_failure(tmp_path):
    """A work item whose session has not registered a conversation yet has no
    transcript; the tick must survive it and pick the session up later."""

    async def scenario():
        resolved = {"path": None}
        broker = stream.StreamBroker(
            tmp_path / "events.jsonl",
            max_subscribers=8,
            transcript_path=lambda ref: resolved["path"],
        )
        subscriber = broker.subscribe(transcripts=["github:o/r#1"])
        for _ in range(4):
            broker.tick()
        assert _drain(subscriber) == []

        later = tmp_path / "late.jsonl"
        later.write_text('{"type":"user"}\n')
        resolved["path"] = later
        for _ in range(stream._TRANSCRIPT_RETRY_TICKS * 2):
            broker.tick()
        with open(later, "a", encoding="utf-8") as handle:
            handle.write('{"type":"assistant"}\n')
        for _ in range(stream._TRANSCRIPT_RETRY_TICKS * 2):
            broker.tick()

        frames = _drain(subscriber)
        assert [f.kind for f in frames] == ["transcript"]
        assert frames[0].data["totalLines"] == 2

    _run(scenario())


def test_a_raising_transcript_resolver_never_kills_the_tick(tmp_path):
    """The resolver reads a registry another process writes; it can fail."""

    def explode(ref):
        raise RuntimeError("registry unreadable")

    async def scenario():
        log = tmp_path / "events.jsonl"
        broker = stream.StreamBroker(log, max_subscribers=8, transcript_path=explode)
        subscriber = broker.subscribe(transcripts=["github:o/r#1"])
        _write(log, {"event": "graph.advanced", "work_item": "github:o/r#1"})
        broker.tick()
        assert [f.kind for f in _drain(subscriber)] == ["log"]

    _run(scenario())


def test_two_tabs_asking_for_the_same_thing_are_two_subscribers(tmp_path):
    """
    Feature: one viewer's tabs do not close each other
      Scenario: two browser tabs watch the same work item
        Given two subscribers registered with identical filters
        When one unsubscribes
        Then the other is still registered and still fed

    Requirement: docs/specs/issue-239/requirements.md R3.5

    A subscriber is an identity, not a value. Field-wise equality would collapse
    identical asks into one entry in the registry — so the second tab would never
    be counted against the cap, and closing either would close both.
    """
    log = tmp_path / "events.jsonl"

    async def scenario():
        broker = stream.StreamBroker(log, max_subscribers=8)
        one = broker.subscribe(work_items=["github:o/r#1"])
        two = broker.subscribe(work_items=["github:o/r#1"])
        assert broker.count == 2

        broker.unsubscribe(one)
        assert broker.count == 1

        _write(log, {"event": "graph.advanced", "work_item": "github:o/r#1"})
        broker.tick()
        assert len(_drain(two)) == 1

    _run(scenario())


# -- self-review findings (issue-239, review round 1) ----------------------------


def test_a_subscriber_that_recovers_can_be_desynced_again(tmp_path):
    """
    Feature: a client is always told when it has a gap
      Scenario: a subscriber overflows, catches up, and falls behind again
        Given a subscriber that overflowed and was told to resynchronise
        When it drains its queue and then overflows a second time
        Then it is told to resynchronise again

    Requirement: docs/specs/issue-239/requirements.md R5.4 (abuse case 5)

    `desynced` means "a resync is already waiting", not "has ever resynced". The
    difference is the whole point: a client that recovered and silently lost
    frames the second time believes it is current and is not — which is the
    screen that looks live and lies.
    """

    async def scenario():
        broker = stream.StreamBroker(tmp_path / "events.jsonl", max_subscribers=8)
        subscriber = broker.subscribe()
        frame = stream.Frame(kind="log", data={"event": "graph.advanced"}, cursor=1)

        for _ in range(stream.QUEUE_SIZE + 1):
            subscriber.offer(frame)
        assert [f.kind for f in _drain(subscriber)] == ["desync"]

        # It caught up. The next overflow must be reported like the first one.
        for _ in range(stream.QUEUE_SIZE + 1):
            subscriber.offer(frame)
        assert "desync" in [f.kind for f in _drain(subscriber)]

    _run(scenario())


def test_a_line_that_never_ends_cannot_grow_without_limit(tmp_path):
    """
    Feature: a broken writer cannot exhaust the service's memory
      Scenario: the log gains bytes that never form a whole record
        Given a log being appended to with no newline
        When the tail reads repeatedly
        Then the held fragment stays bounded and the tail resynchronises

    Requirement: docs/specs/issue-239/requirements.md R5.4 (abuse case 5)

    The subscriber queues are bounded; this is the other buffer, and it was not.
    A partial line is held so a mid-write read does not lose the record — but
    "held" has to have a ceiling, or a writer that never terminates a line (or a
    corrupted file) grows it until the process dies.
    """
    log = tmp_path / "events.jsonl"
    tail = stream.LogTail(log)
    with open(log, "ab") as handle:
        for _ in range(400):
            handle.write(b"x" * 4096)
            handle.flush()
            assert list(tail.read()) == []
            assert len(tail._partial) <= stream.MAX_PARTIAL_BYTES

    # And it recovers: a whole record after the garbage is still delivered.
    with open(log, "ab") as handle:
        handle.write(b'\n{"event":"graph.advanced"}\n')
    assert [r.data["event"] for r in tail.read()] == ["graph.advanced"]


def test_a_record_appended_during_replay_is_not_lost(tmp_path):
    """
    Feature: the handover from replay to live loses nothing
      Scenario: a record is appended between the replay read and the live tail
        Given a subscriber replaying from a cursor
        When a record is appended after the replay window was measured
        Then the live tailer delivers it, rather than skipping past it

    Requirement: docs/specs/issue-239/requirements.md R1.5

    The shared tailer is positioned at EOF when the FIRST subscriber registers,
    and the replay window ends at exactly that offset. Positioning it after the
    replay instead leaves a gap the width of however long the replay took — and a
    dropped record is the one failure `Last-Event-ID` exists to prevent.
    """

    async def scenario():
        log = tmp_path / "events.jsonl"
        _write(log, {"event": "graph.advanced", "n": 1})
        boundary = log.stat().st_size

        broker = stream.StreamBroker(log, max_subscribers=8)
        subscriber = broker.subscribe()
        # Registering positions the shared tail; the replay window is [0, here).
        assert broker.tail_offset() == boundary

        _write(log, {"event": "graph.advanced", "n": 2})
        broker.tick()

        # n=1 is the replay's to deliver, n=2 is the tailer's. Neither is both,
        # and neither is nobody's.
        assert [f.data["n"] for f in _drain(subscriber)] == [2]
        replayed = [
            r.data["n"] for r in stream.LogTail(log).read() if r.cursor <= boundary
        ]
        assert replayed == [1]

    _run(scenario())


def test_counting_transcript_lines_does_not_re_read_the_whole_file(tmp_path):
    """
    Feature: watching a long session stays cheap
      Scenario: a watched transcript grows repeatedly
        Given a transcript that has already reached a few thousand lines
        When it gains one line at a time
        Then the whole-file counter is never called again — only the new bytes are

    Requirement: docs/specs/issue-239/requirements.md §Non-functional (cost)

    An agent's JSONL reaches megabytes over a long session. Counting its lines
    from scratch twice a second is real I/O for a number that only ever moves by
    a handful, so the count is carried and only the appended bytes are counted.
    Asserted at the seam — `_count_lines` reads the whole file, and after the
    baseline it must not be reached at all.
    """
    transcript = tmp_path / "session.jsonl"
    transcript.write_bytes(b'{"type":"user"}\n' * 5000)

    async def scenario():
        broker = stream.StreamBroker(
            tmp_path / "events.jsonl",
            max_subscribers=8,
            transcript_path=lambda ref: transcript,
        )
        subscriber = broker.subscribe(transcripts=["github:o/r#1"])
        broker.tick()  # the baseline may read the whole file, once

        def explode(*args, **kwargs):
            raise AssertionError("the whole transcript was re-read after the baseline")

        original = stream._count_lines
        stream._count_lines = explode
        try:
            for _ in range(5):
                with open(transcript, "ab") as handle:
                    handle.write(b'{"type":"assistant"}\n')
                broker.tick()
        finally:
            stream._count_lines = original

        assert [f.data["totalLines"] for f in _drain(subscriber)] == [
            5001,
            5002,
            5003,
            5004,
            5005,
        ]

    _run(scenario())
