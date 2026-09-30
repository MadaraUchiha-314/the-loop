"""Unit tests for the manager's stream fan-in (issue-374, R2.8, T1).

The composite cursor grammar, the SSE parser, the fleet broker (stamping, the
per-member cursor, a member's desync, transcripts, one upstream per live member
whatever the subscriber count, reconnection with backoff and resume), and
`serve_fleet`'s replay per source — all over a scripted opener, so no socket.

Spec: docs/specs/issue-374/design.md § 5.
"""

from __future__ import annotations

import asyncio
import email.message
import json
import threading
import time
import urllib.error
from typing import List

import pytest

from the_loop.manager import stream as fleet_stream
from the_loop.manager.fleet import Fleet, TransportError
from the_loop.manager.stream import (
    FleetBroker,
    FleetCursor,
    encode_cursor,
    parse_fleet_cursor,
    parse_sse,
    serve_fleet,
)

A = "http://a:1"


def _sse(event_id, kind, data):
    return [
        f"id: {event_id}\n".encode(),
        f"event: {kind}\n".encode(),
        f"data: {json.dumps(data)}\n".encode(),
        b"\n",
    ]


class FakeTransport:
    """Every registered URL answers as a live worker."""

    def __init__(self, names):
        self.names = names

    def __call__(self, method, url, body, timeout):
        base, _, rest = url.partition("/api/v1")
        name = self.names.get(base)
        if name is None:
            raise TransportError("connection refused")
        if rest.startswith("/instance"):
            return 200, json.dumps(
                {
                    "name": name,
                    "role": "worker",
                    "scope": {"mode": "open"},
                    "managed": [],
                }
            ).encode()
        return 200, json.dumps({"version": "1"}).encode()


class ScriptedOpener:
    """Each call hands out the next script: a list of lines, then a fate."""

    def __init__(self):
        self.calls: List[tuple] = []
        self.scripts: List[
            tuple
        ] = []  # (lines, fate) — fate: "hold" | "close" | Exception
        self.release = threading.Event()

    def __call__(self, url, last_event_id, timeout):
        self.calls.append((url, last_event_id, timeout))
        lines, fate = self.scripts.pop(0) if self.scripts else ([], "hold")
        if isinstance(fate, Exception):
            raise fate

        def gen():
            yield from lines
            if fate == "hold":
                self.release.wait(timeout=5)
            # "close": the body simply ends

        return gen()


def _config(members, interval=15):
    return {
        "instance": {
            "name": "hq",
            "role": "manager",
            "manager": {
                "instances": [{"name": n, "url": u} for n, u in members],
                "timeoutSeconds": 1,
                "probeIntervalSeconds": interval,
            },
        }
    }


@pytest.fixture
def quiet(monkeypatch):
    emitted = []
    monkeypatch.setattr(
        fleet_stream.eventlog, "emit", lambda *a, **k: emitted.append((a[0], k))
    )
    from the_loop.manager import fleet as fleet_mod

    monkeypatch.setattr(
        fleet_mod.eventlog, "emit", lambda *a, **k: emitted.append((a[0], k))
    )
    return emitted


def _broker(tmp_path, opener, members=(("laptop-a", A),), sleeps=None, dead=()):
    config = _config(list(members))
    fleet = Fleet(
        lambda: config,
        transport=FakeTransport({u: n for n, u in members if n not in dead}),
    )
    log = tmp_path / "events.jsonl"
    log.write_text("")
    return FleetBroker(
        fleet,
        log,
        "hq",
        max_subscribers=8,
        opener=opener,
        keepalive_hint=1,
        sleep=(lambda s: sleeps.append(s))
        if sleeps is not None
        else (lambda s: time.sleep(0.001)),
    ), log


async def _settle(broker, ticks=3):
    for _ in range(ticks):
        await asyncio.sleep(0.05)
        broker.tick()


# -- the cursor ---------------------------------------------------------------------------


def _cursor(raw) -> FleetCursor:
    parsed = parse_fleet_cursor(raw)
    assert parsed is not None
    return parsed


def test_the_composite_cursor_grammar():
    assert parse_fleet_cursor(None) is None
    assert _cursor("laptop-a=4096,hq=77").offsets == {
        "laptop-a": 4096,
        "hq": 77,
    }
    assert _cursor("12").desync == "bad-cursor"  # a worker's cursor on a manager
    assert _cursor("").desync == "bad-cursor"
    assert _cursor("Laptop=1").desync == "bad-cursor"
    assert _cursor("a=-1").desync == "bad-cursor"
    assert encode_cursor({"hq": 2, "a": 1}) == "a=1,hq=2"


def test_the_sse_parser_reads_frames_and_skips_comments():
    lines = (
        [b"retry: 3000\n", b"\n", b": keep-alive\n", b"\n"]
        + _sse(7, "log", {"x": 1})
        + [b"data: a\n", b"data: b\n", b"\n"]
    )
    frames = list(parse_sse(iter(lines)))
    assert frames == [("7", "log", '{"x": 1}'), (None, "message", "a\nb")]


# -- the broker -------------------------------------------------------------------------------


def test_frames_are_stamped_and_carry_the_per_member_cursor(tmp_path, quiet):
    opener = ScriptedOpener()
    opener.scripts.append(
        (
            _sse(
                4120,
                "log",
                {
                    "event": "graph.advanced",
                    "work_item": "github:octo/repo#1",
                    "instance": "liar",
                },
            ),
            "hold",
        )
    )
    broker, log = _broker(tmp_path, opener)

    async def main():
        sub = broker.subscribe()
        await _settle(broker)
        log.write_text(json.dumps({"event": "config.updated", "ts": "t"}) + "\n")
        await _settle(broker)
        frames = []
        while not sub.queue.empty():
            frames.append(sub.queue.get_nowait())
        broker.unsubscribe(sub)
        return frames

    frames = asyncio.run(main())
    opener.release.set()
    kinds = [(f.kind, f.data.get("instance")) for f in frames]
    assert ("log", "laptop-a") in kinds and ("log", "hq") in kinds
    member = next(f for f in frames if f.data.get("instance") == "laptop-a")
    assert member.data["event"] == "graph.advanced"  # R6.3: the stamp overwrote "liar"
    assert "laptop-a=4120" in member.cursor and "hq=" in member.cursor
    own = next(f for f in frames if f.data.get("instance") == "hq")
    assert _cursor(own.cursor).offsets["hq"] == log.stat().st_size
    assert opener.calls[0] == (A + "/api/v1/stream", None, 3)


def test_one_upstream_per_live_member_whatever_the_subscriber_count(tmp_path, quiet):
    opener = ScriptedOpener()
    broker, _ = _broker(
        tmp_path,
        opener,
        members=(("laptop-a", A), ("ci-box", "http://b:1"), ("cloud-1", "http://c:1")),
        dead=("cloud-1",),
    )

    async def main():
        subs = [broker.subscribe() for _ in range(4)]
        await _settle(broker)
        count = broker.upstream_count
        calls = len(opener.calls)
        for sub in subs:
            broker.unsubscribe(sub)
        return count, calls, broker.upstream_count

    count, calls, after = asyncio.run(main())
    opener.release.set()
    # Three registered, two live: two upstreams; cloud-1 waits on its probe.
    assert count == 3 and calls == 2 and after == 0


def test_a_members_desync_and_transcript_reach_the_subscriber(tmp_path, quiet):
    opener = ScriptedOpener()
    opener.scripts.append(
        (
            _sse(9, "transcript", {"ref": "github:octo/repo#1", "totalLines": 12})
            + [b"event: desync\n", b'data: {"reason": "replay-window"}\n', b"\n"],
            "hold",
        )
    )
    broker, _ = _broker(tmp_path, opener)

    async def main():
        sub = broker.subscribe(transcripts=["github:octo/repo#1"])
        await _settle(broker)
        frames = []
        while not sub.queue.empty():
            frames.append(sub.queue.get_nowait())
        broker.unsubscribe(sub)
        return frames

    frames = asyncio.run(main())
    opener.release.set()
    assert [(f.kind, f.data) for f in frames] == [
        ("transcript", {"ref": "github:octo/repo#1", "totalLines": 12}),
        ("desync", {"reason": "replay-window", "instance": "laptop-a"}),
    ]


def test_a_dropped_upstream_reconnects_with_backoff_and_resumes(tmp_path, quiet):
    """Abuse case 4: bounded backoff, and the resume names the last id seen."""
    opener = ScriptedOpener()
    opener.scripts.append((_sse(10, "log", {"event": "x"}), "close"))
    opener.scripts.append(([], RuntimeError("reset")))
    opener.scripts.append((_sse(11, "log", {"event": "y"}), "hold"))
    sleeps: List[float] = []
    broker, _ = _broker(tmp_path, opener, sleeps=sleeps)

    async def main():
        sub = broker.subscribe()
        for _ in range(20):
            await asyncio.sleep(0.05)
            broker.tick()
            if len(opener.calls) >= 3:
                break
        await _settle(broker)
        frames = []
        while not sub.queue.empty():
            frames.append(sub.queue.get_nowait())
        broker.unsubscribe(sub)
        return frames

    frames = asyncio.run(main())
    opener.release.set()
    assert [c[1] for c in opener.calls[:3]] == [None, "10", "10"]
    assert sleeps[:2] == [1.0, 2.0]
    assert [f.data["event"] for f in frames if f.kind == "log"] == ["x", "y"]


def test_a_member_without_a_stream_is_left_to_the_probe_cycle(tmp_path, quiet):
    opener = ScriptedOpener()
    opener.scripts.append(
        ([], urllib.error.HTTPError(A, 404, "off", email.message.Message(), None))
    )
    sleeps: List[float] = []
    broker, _ = _broker(tmp_path, opener, sleeps=sleeps)

    async def main():
        sub = broker.subscribe()
        for _ in range(20):
            await asyncio.sleep(0.05)
            if sleeps:
                break
        broker.unsubscribe(sub)

    asyncio.run(main())
    opener.release.set()
    assert sleeps and sleeps[0] == 15  # the probe interval, not the backoff


# -- serve_fleet -------------------------------------------------------------------------------


def _collect(gen, n):
    async def main():
        out = []
        async for chunk in gen:
            out.append(chunk)
            if len(out) >= n:
                break
        return out

    return asyncio.run(main())


def test_a_bare_integer_cursor_is_one_desync(tmp_path, quiet):
    opener = ScriptedOpener()
    broker, _ = _broker(tmp_path, opener)

    async def main():
        sub = broker.subscribe()
        gen = serve_fleet(broker, sub, cursor=parse_fleet_cursor("12"), keep_alive=1)
        first = await gen.__anext__()
        second = await gen.__anext__()
        await gen.aclose()
        return first, second

    first, second = asyncio.run(main())
    opener.release.set()
    assert first.startswith("event: desync") and '"reason":"bad-cursor"' in first
    assert second.startswith("retry:")


def test_own_offset_replays_the_managers_log_and_a_members_offset_asks_the_member(
    tmp_path, quiet
):
    """R2.8: replay per source, up to the boundary each stood at."""
    opener = ScriptedOpener()
    # The shared upstream delivers id 20 first, so the boundary for laptop-a is 20;
    # the replay connection (Last-Event-ID: 10) then serves 15 and 20 and is closed.
    opener.scripts.append((_sse(20, "log", {"event": "live"}), "hold"))
    opener.scripts.append(
        (
            _sse(15, "log", {"event": "old"})
            + _sse(20, "log", {"event": "live"})
            + _sse(25, "log", {"event": "later"}),
            "hold",
        )
    )
    broker, log = _broker(tmp_path, opener)
    log.write_text(
        json.dumps({"event": "one"}) + "\n" + json.dumps({"event": "two"}) + "\n"
    )
    first_line = len(json.dumps({"event": "one"}) + "\n")

    async def main():
        sub = broker.subscribe()
        await _settle(broker)
        while not sub.queue.empty():
            sub.queue.get_nowait()
        cursor = FleetCursor(offsets={"hq": first_line, "laptop-a": 10})
        gen = serve_fleet(broker, sub, cursor=cursor, keep_alive=1)
        chunks = []
        for _ in range(4):
            chunks.append(await gen.__anext__())
        await gen.aclose()
        return chunks

    chunks = asyncio.run(main())
    opener.release.set()
    assert chunks[0].startswith("retry:")
    events = [json.loads(c.split("data: ", 1)[1])["event"] for c in chunks[1:]]
    assert events == [
        "two",
        "old",
        "live",
    ]  # own log after the offset, then the member's up to the boundary
    assert all('"instance":' in c for c in chunks[1:])
    assert opener.calls[1][1] == "10"


def test_a_member_that_desyncs_on_replay_makes_one_desync(tmp_path, quiet):
    opener = ScriptedOpener()
    opener.scripts.append((_sse(20, "log", {"event": "live"}), "hold"))
    opener.scripts.append(
        ([b"event: desync\n", b'data: {"reason": "replay-window"}\n', b"\n"], "hold")
    )
    broker, _ = _broker(tmp_path, opener)

    async def main():
        sub = broker.subscribe()
        await _settle(broker)
        gen = serve_fleet(
            broker, sub, cursor=FleetCursor(offsets={"laptop-a": 1}), keep_alive=1
        )
        first = await gen.__anext__()
        await gen.aclose()
        return first

    first = asyncio.run(main())
    opener.release.set()
    assert first.startswith("event: desync") and "member" in first


def test_an_oversized_frame_is_dropped_not_held():
    """Security review: a frame past MAX_PARTIAL_BYTES is discarded whole."""
    from the_loop.api.stream import MAX_PARTIAL_BYTES

    huge = b"data: " + b"x" * (MAX_PARTIAL_BYTES + 10) + b"\n"
    lines = [b"event: log\n", huge, b"\n"] + _sse(3, "log", {"event": "after"})
    frames = list(parse_sse(iter(lines)))
    assert frames == [("3", "log", '{"event": "after"}')]


def test_own_frames_in_one_batch_carry_their_own_offsets(tmp_path, quiet):
    """Self-review: a drop mid-batch resumes after the frame last read, not the batch."""
    opener = ScriptedOpener()
    broker, log = _broker(tmp_path, opener)
    one = json.dumps({"event": "one"}) + "\n"
    two = json.dumps({"event": "two"}) + "\n"

    async def main():
        sub = broker.subscribe()
        await _settle(broker)
        log.write_text(one + two)
        await _settle(broker)
        frames = []
        while not sub.queue.empty():
            frames.append(sub.queue.get_nowait())
        broker.unsubscribe(sub)
        return frames

    frames = asyncio.run(main())
    opener.release.set()
    own = [f for f in frames if f.kind == "log" and f.data.get("instance") == "hq"]
    assert [f.data["event"] for f in own] == ["one", "two"]
    assert _cursor(own[0].cursor).offsets["hq"] == len(one)
    assert _cursor(own[1].cursor).offsets["hq"] == len(one) + len(two)


def test_replayed_frames_carry_the_position_after_each_record(tmp_path, quiet):
    """Self-review: a drop mid-replay resumes exactly there, not at the boundary."""
    opener = ScriptedOpener()
    opener.scripts.append((_sse(20, "log", {"event": "live"}), "hold"))
    opener.scripts.append(
        (_sse(15, "log", {"event": "old"}) + _sse(20, "log", {"event": "live"}), "hold")
    )
    broker, log = _broker(tmp_path, opener)
    one = json.dumps({"event": "one"}) + "\n"
    two = json.dumps({"event": "two"}) + "\n"
    log.write_text(one + two)

    async def main():
        sub = broker.subscribe()
        await _settle(broker)
        while not sub.queue.empty():
            sub.queue.get_nowait()
        gen = serve_fleet(
            broker,
            sub,
            cursor=FleetCursor(offsets={"hq": 0, "laptop-a": 10}),
            keep_alive=1,
        )
        chunks = [await gen.__anext__() for _ in range(5)]
        await gen.aclose()
        return chunks

    chunks = asyncio.run(main())
    opener.release.set()
    ids = [c.split("\n")[0][4:] for c in chunks[1:]]
    # own "one" (hq after one, laptop-a still the client's 10), own "two", then the
    # member's 15 and 20.
    assert _cursor(ids[0]).offsets == {"hq": len(one), "laptop-a": 10}
    assert _cursor(ids[1]).offsets == {"hq": len(one) + len(two), "laptop-a": 10}
    assert _cursor(ids[2]).offsets["laptop-a"] == 15
    assert _cursor(ids[3]).offsets["laptop-a"] == 20


def test_a_dead_upstream_thread_is_replaced_on_reconcile(tmp_path, quiet):
    """Self-review round 2: a thread that ended is replaced, not mourned."""
    opener = ScriptedOpener()
    broker, _ = _broker(tmp_path, opener)

    async def main():
        sub = broker.subscribe()
        await _settle(broker)
        dead = threading.Thread(target=lambda: None)
        dead.start()
        dead.join()
        old = broker._upstreams["laptop-a"]
        old.thread = dead
        broker.reconcile_upstreams()
        replaced = (
            broker._upstreams["laptop-a"] is not old
            and broker._upstreams["laptop-a"].thread.is_alive()
        )
        broker.unsubscribe(sub)
        return replaced

    assert asyncio.run(main())
    opener.release.set()


def test_a_restarted_broker_connects_fresh(tmp_path, quiet):
    """Self-review round 2: no stale Last-Event-ID and no old queue after stop/start."""
    opener = ScriptedOpener()
    opener.scripts.append((_sse(30, "log", {"event": "before"}), "hold"))
    broker, _ = _broker(tmp_path, opener)

    async def main():
        sub = broker.subscribe()
        await _settle(broker)
        broker.unsubscribe(sub)  # last subscriber: stop
        assert broker.offsets() == {"hq": broker.tail_offset()}
        sub2 = broker.subscribe()
        await _settle(broker)
        frames = []
        while not sub2.queue.empty():
            frames.append(sub2.queue.get_nowait())
        broker.unsubscribe(sub2)
        return frames

    frames = asyncio.run(main())
    opener.release.set()
    assert [c[1] for c in opener.calls[:2]] == [None, None]
    assert all(f.data.get("event") != "before" for f in frames)
