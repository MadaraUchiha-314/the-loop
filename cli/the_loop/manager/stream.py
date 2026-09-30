"""The manager's stream: every member's frames fanned into one (issue-374, R2.8).

A worker's ``GET /api/v1/stream`` tails one file. A manager's is the same route over a
:class:`FleetBroker`: the manager's **own** event log, tailed as a worker tails it, plus
**one upstream SSE connection per live member** — opened by the manager as a client of
the member's own stream, on a thread, however many browsers watch the manager. Every
``log`` frame's record is stamped ``instance`` with the registered name (R6.3); a
member's ``transcript`` frame passes through; a member's ``desync`` becomes the
manager's.

**The cursor is per member** (decision-138 D8). A frame's ``id`` is
``name=offset(,name=offset)*`` over every source that has delivered, the manager's own
log under the manager's name. ``Last-Event-ID`` in that grammar is resolved member by
member — each named member is asked to replay from its own offset — and a member that
cannot (it answers ``desync``, or its cursor is behind the replay window) makes the
manager's answer one ``desync`` frame, after which the browser refetches and continues
as it does today. A cursor outside the grammar — a worker's bare integer pasted into a
manager — is the same ``desync``.

**Reconnection is bounded.** A dropped upstream is retried with backoff
``1, 2, 4, … 30 s`` while the member's probe is live, then left to the probe cycle. An
upstream that stops sending is detected by the member's own keep-alives: three missed
ones close the socket and reconnect. The threads start with the first subscriber and
stop with the last, exactly as the worker's tailer task does; ``maxSubscribers`` bounds
the manager's own subscribers, and the upstream count is the live-member count
whatever the subscriber count.

Spec: docs/specs/issue-374/design.md § 5.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

from .. import eventlog
from ..api.stream import (
    MAX_PARTIAL_BYTES,
    QUEUE_SIZE,
    REPLAY_BYTES,
    RETRY_MS,
    TICK_SECONDS,
    Frame,
    LogTail,
    Subscriber,
    encode_frame,
    keepalive,
    matches,
)
from ..instance import Member
from .fleet import Fleet

logger = logging.getLogger("the-loop.manager")

__all__ = [
    "FleetBroker",
    "FleetCursor",
    "MAX_BACKOFF_SECONDS",
    "Opener",
    "encode_cursor",
    "parse_fleet_cursor",
    "serve_fleet",
    "urllib_opener",
]

#: The longest wait between two reconnection attempts to a member's stream.
MAX_BACKOFF_SECONDS = 30.0

#: How many keep-alive intervals of silence close an upstream connection. The
#: member sends a comment every ``keepAliveSeconds`` (15 by default); three missed
#: is a dead socket, not a quiet workstation.
MISSED_KEEPALIVES = 3
_DEFAULT_KEEPALIVE_HINT = 15.0

#: ``(url, last_event_id, timeout) -> iterator of raw lines`` — one upstream SSE body,
#: line by line. Injected so the tests script a member's stream without a socket.
Opener = Callable[[str, Optional[str], float], Iterator[bytes]]

_CURSOR_PART = re.compile(r"^([a-z0-9][a-z0-9-]{0,39})=(\d+)$")


def urllib_opener(
    url: str, last_event_id: Optional[str], timeout: float
) -> Iterator[bytes]:
    """The default opener: stdlib, no caller headers, no redirects, a socket timeout
    as the watchdog, and no line longer than :data:`MAX_PARTIAL_BYTES`."""
    from .fleet import _opener

    request = urllib.request.Request(url, method="GET")
    request.add_header("Accept", "text/event-stream")
    request.add_header("Cache-Control", "no-cache")
    if last_event_id is not None:
        request.add_header("Last-Event-ID", last_event_id)
    response = _opener.open(request, timeout=timeout)  # noqa: S310 — http(s) URL from the operator's config
    try:
        while True:
            line = response.readline(MAX_PARTIAL_BYTES + 1)
            if not line:
                return
            yield line
    finally:
        response.close()


# -- the cursor -----------------------------------------------------------------


@dataclass(frozen=True)
class FleetCursor:
    """``Last-Event-ID`` as the manager reads it: an offset per named source.

    ``desync`` carries the reason a cursor could not be honoured at all — a bare
    integer, a name outside the grammar — so the route still accepts the connection
    and answers with one ``desync`` frame rather than a 400: the browser's correct
    response to a cursor it cannot use is to refetch, and that path already exists.
    """

    offsets: Dict[str, int] = field(default_factory=dict)
    desync: str = ""


def parse_fleet_cursor(raw: Optional[str]) -> Optional[FleetCursor]:
    """``None`` for a fresh connection; otherwise the per-source offsets, or a desync."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return FleetCursor(desync="bad-cursor")
    offsets: Dict[str, int] = {}
    for part in text.split(","):
        match = _CURSOR_PART.match(part.strip())
        if not match:
            return FleetCursor(desync="bad-cursor")
        offsets[match.group(1)] = int(match.group(2))
    return FleetCursor(offsets=offsets)


def encode_cursor(offsets: Dict[str, int]) -> str:
    return ",".join(f"{name}={offset}" for name, offset in sorted(offsets.items()))


# -- one upstream connection ----------------------------------------------------------


@dataclass
class _Event:
    """One frame from a member, or a fact about the connection."""

    source: str
    kind: str  # log | transcript | desync
    data: Dict[str, Any]
    cursor: Optional[int] = None


def parse_sse(lines: Iterator[bytes]) -> Iterator[Tuple[Optional[str], str, str]]:
    """``(id, event, data)`` per frame; comments and ``retry:`` are skipped.

    A frame is held for at most :data:`MAX_PARTIAL_BYTES` — the tailer's own bound
    for an unterminated line: a member that never ends a frame, or ends one far
    larger than any record ``eventlog`` writes, has that frame dropped rather than
    the manager's memory grown by it.
    """
    event_id: Optional[str] = None
    kind = "message"
    data: List[str] = []
    held = 0
    for raw in lines:
        if held > MAX_PARTIAL_BYTES:
            # Oversized: discard until the frame ends, then start clean.
            if raw in (b"\n", b"\r\n"):
                event_id, kind, data, held = None, "message", [], 0
            continue
        held += len(raw)
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if line == "":
            if data:
                yield event_id, kind, "\n".join(data)
            event_id, kind, data, held = None, "message", [], 0
            continue
        if line.startswith(":"):
            continue
        name, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if name == "id":
            event_id = value
        elif name == "event":
            kind = value
        elif name == "data":
            data.append(value)


class _Upstream:
    """One member's stream, read on a thread into the broker's queue."""

    def __init__(
        self,
        member: Member,
        fleet: Fleet,
        opener: Opener,
        sink: "queue.Queue[_Event]",
        *,
        last_id: Optional[int] = None,
        keepalive_hint: float = _DEFAULT_KEEPALIVE_HINT,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.member = member
        self.fleet = fleet
        self.opener = opener
        self.sink = sink
        self.last_id = last_id
        self.keepalive_hint = keepalive_hint
        self._sleep = sleep
        self._stop = threading.Event()
        self.thread = threading.Thread(
            target=self._run, name=f"the-loop-stream-{member.name}", daemon=True
        )
        self.attempts = 0

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            if not self.fleet.probe(self.member).live:
                # Left to the probe cycle: retry no sooner than the next probe.
                self._sleep(self.fleet.config.probe_interval_seconds)
                continue
            try:
                self.attempts += 1
                self._read_once()
                backoff = 1.0
            except _Disabled:
                logger.info(
                    "%s serves no stream (service.stream.enabled is false); "
                    "its events reach /api/v1/events only",
                    self.member.name,
                )
                self._sleep(self.fleet.config.probe_interval_seconds)
            except Exception as exc:  # noqa: BLE001 — every failure is a reconnect
                if self._stop.is_set():
                    break
                logger.warning(
                    "%s stream dropped (%s); reconnecting in %.0fs",
                    self.member.name,
                    exc,
                    backoff,
                )
                self._sleep(backoff)
                backoff = min(MAX_BACKOFF_SECONDS, backoff * 2)

    def _read_once(self) -> None:
        url = self.member.url + "/api/v1/stream"
        last = str(self.last_id) if self.last_id is not None else None
        timeout = self.keepalive_hint * MISSED_KEEPALIVES
        try:
            lines = self.opener(url, last, timeout)
            for event_id, kind, payload in parse_sse(lines):
                if self._stop.is_set():
                    return
                self._deliver(event_id, kind, payload)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise _Disabled() from exc
            raise
        except socket.timeout as exc:
            raise RuntimeError("no keep-alive") from exc
        # The body ended: the member closed it — reconnect after the backoff.
        raise RuntimeError("connection closed")

    def _deliver(self, event_id: Optional[str], kind: str, payload: str) -> None:
        try:
            data = json.loads(payload)
        except ValueError:
            return
        if not isinstance(data, dict):
            return
        cursor: Optional[int] = None
        if event_id is not None and event_id.isdigit():
            cursor = int(event_id)
            self.last_id = cursor
        if kind == "log":
            data["instance"] = self.member.name
        elif kind == "desync":
            # The member could not honour our resume; every subscriber refetches.
            pass
        elif kind != "transcript":
            return
        self.sink.put(_Event(self.member.name, kind, data, cursor))


class _Disabled(Exception):
    """The member answers 404: `service.stream.enabled` is false there."""


# -- the broker ---------------------------------------------------------------------------


class FleetBroker:
    """One own tailer, one upstream per live member, one bounded queue per subscriber.

    The same subscriber semantics as :class:`~the_loop.api.stream.StreamBroker` — the
    capacity check at :meth:`subscribe`, the task starting with the first subscriber
    and stopping with the last — over two sources instead of one file.
    """

    def __init__(
        self,
        fleet: Fleet,
        own_log: Union[str, Path],
        own_name: str,
        max_subscribers: int,
        transcript_path=None,
        *,
        opener: Opener = urllib_opener,
        keepalive_hint: float = _DEFAULT_KEEPALIVE_HINT,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.fleet = fleet
        self.own_name = own_name
        self.log_path = Path(own_log)
        self.max_subscribers = max(1, int(max_subscribers))
        self._transcript_path = transcript_path
        self._opener = opener
        self._keepalive_hint = keepalive_hint
        self._sleep = sleep
        self._subscribers: Set[Subscriber] = set()
        self._task: Optional[asyncio.Task] = None
        self._tail = LogTail(self.log_path)
        self._queue: "queue.Queue[_Event]" = queue.Queue()
        self._upstreams: Dict[str, _Upstream] = {}
        #: The last offset seen per source — the composite cursor every frame carries.
        self._offsets: Dict[str, int] = {}
        self._sizes: Dict[str, Tuple[int, int]] = {}
        self._ticks = 0

    # -- the composite cursor -------------------------------------------------------------

    def offsets(self) -> Dict[str, int]:
        """Where every source stands now — the boundary a replay ends at."""
        current = dict(self._offsets)
        current[self.own_name] = self._tail.offset
        return current

    def tail_offset(self) -> int:
        return self._tail.offset

    @property
    def count(self) -> int:
        return len(self._subscribers)

    @property
    def at_capacity(self) -> bool:
        return self.count >= self.max_subscribers

    @property
    def upstream_count(self) -> int:
        return len(self._upstreams)

    # -- lifecycle ------------------------------------------------------------------------------

    def subscribe(
        self, work_items: Sequence[str] = (), transcripts: Sequence[str] = ()
    ) -> Subscriber:
        if self.at_capacity:
            raise RuntimeError(
                f"at capacity: {self.count} of {self.max_subscribers} stream "
                "connections are open (service.stream.maxSubscribers)"
            )
        subscriber = Subscriber(
            queue=asyncio.Queue(maxsize=QUEUE_SIZE),
            work_items=list(work_items),
            transcripts=list(transcripts),
        )
        first = not self._subscribers
        self._subscribers.add(subscriber)
        if first:
            self.start()
        return subscriber

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.discard(subscriber)
        if not self._subscribers:
            self.stop()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._tail.seek_to_end()
            self.reconcile_upstreams()
            self._task = asyncio.ensure_future(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        for upstream in self._upstreams.values():
            upstream.stop()
        self._upstreams.clear()

    def reconcile_upstreams(self) -> None:
        """One upstream per live member: start the new, stop the unregistered."""
        wanted = {member.name: member for member in self.fleet.members()}
        for name in list(self._upstreams):
            if name not in wanted or self._upstreams[name].stopped:
                self._upstreams.pop(name).stop()
        for name, member in wanted.items():
            if name in self._upstreams:
                continue
            upstream = _Upstream(
                member,
                self.fleet,
                self._opener,
                self._queue,
                last_id=self._offsets.get(name),
                keepalive_hint=self._keepalive_hint,
                sleep=self._sleep,
            )
            self._upstreams[name] = upstream
            upstream.start()

    # -- the tick -----------------------------------------------------------------------------------

    async def _run(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:  # noqa: BLE001 — o11y must never kill the tailer
                logger.exception("fleet stream tick failed; continuing")
            await asyncio.sleep(TICK_SECONDS)

    def tick(self) -> None:
        """Drain the members' queue and the own log once; fan out to everyone."""
        self._ticks += 1
        if self._ticks % 10 == 0:
            self.reconcile_upstreams()
        for record in self._tail.read():
            # Each record's OWN offset (the tail advances to the chunk's end before
            # yielding), so a client that drops mid-batch resumes after the frame it
            # last read, not after the batch — the worker's `record.cursor` rule.
            offsets = dict(self._offsets)
            offsets[self.own_name] = record.cursor
            self._offer(
                Frame(
                    kind="log",
                    data=dict(record.data, instance=self.own_name),
                    cursor=encode_cursor(offsets),
                ),
                by_work_item=True,
            )
        while True:
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                break
            if event.cursor is not None:
                self._offsets[event.source] = event.cursor
            cursor = encode_cursor(self.offsets())
            if event.kind == "log":
                self._offer(
                    Frame(kind="log", data=event.data, cursor=cursor), by_work_item=True
                )
            elif event.kind == "transcript":
                ref = str(event.data.get("ref") or "")
                frame = Frame(kind="transcript", data=event.data)
                for subscriber in list(self._subscribers):
                    if ref in subscriber.transcripts:
                        subscriber.offer(frame)
            else:
                reason = str(event.data.get("reason") or "member")
                frame = Frame(
                    kind="desync",
                    data={"reason": reason, "instance": event.source},
                )
                for subscriber in list(self._subscribers):
                    subscriber.offer(frame)
        self._tick_transcripts()

    def _offer(self, frame: Frame, *, by_work_item: bool) -> None:
        for subscriber in list(self._subscribers):
            if not by_work_item or matches(frame.data, subscriber.work_items):
                subscriber.offer(frame)

    def _tick_transcripts(self) -> None:
        """The manager's own watched transcripts — the worker's rule, verbatim."""
        if self._transcript_path is None:
            return
        import os

        watched = {ref for s in self._subscribers for ref in s.transcripts}
        for ref in watched:
            known = self._sizes.get(ref)
            if known is None and self._ticks % 10 not in (0, 1):
                continue
            try:
                path = self._transcript_path(ref)
            except Exception:  # noqa: BLE001
                path = None
            if not path:
                continue
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if known is not None and size == known[0]:
                continue
            try:
                with open(path, "rb") as handle:
                    if known is None or size < known[0]:
                        lines = sum(1 for _ in handle)
                    else:
                        handle.seek(known[0])
                        lines = known[1] + handle.read().count(b"\n")
            except OSError:
                continue
            self._sizes[ref] = (size, lines)
            if known is None:
                continue
            frame = Frame(kind="transcript", data={"ref": ref, "totalLines": lines})
            for subscriber in list(self._subscribers):
                if ref in subscriber.transcripts:
                    subscriber.offer(frame)


# -- one connection ---------------------------------------------------------------------------


def _replay_member(
    broker: FleetBroker, name: str, offset: int, boundary: Optional[int]
) -> Iterator[Frame]:
    """A member's records between ``offset`` and the shared upstream's position.

    A temporary connection with ``Last-Event-ID: offset``, read until the frames reach
    ``boundary`` — where the shared upstream already stands — then closed. Raises
    :class:`_Resync` when the member answers ``desync`` (its window is gone) or the
    boundary is unknown (the shared upstream has not delivered yet, so nothing says
    where replay would end).
    """
    member = broker.fleet.config.member(name)
    if member is None or boundary is None or not broker.fleet.probe(member).live:
        raise _Resync("replay-window")
    if boundary <= offset:
        return
    if boundary - offset > REPLAY_BYTES:
        raise _Resync("replay-window")
    url = member.url + "/api/v1/stream"
    lines = broker._opener(url, str(offset), broker.fleet.config.timeout_seconds)
    for event_id, kind, payload in parse_sse(lines):
        if kind == "desync":
            raise _Resync("member")
        if kind != "log" or event_id is None or not event_id.isdigit():
            continue
        cursor = int(event_id)
        if cursor > boundary:
            break
        try:
            data = json.loads(payload)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        data["instance"] = name
        yield Frame(kind="log", data=data, cursor=cursor)
        if cursor == boundary:
            break


class _Resync(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def serve_fleet(
    broker: FleetBroker,
    subscriber: Subscriber,
    cursor: Optional[FleetCursor] = None,
    keep_alive: int = 15,
):
    """One subscriber's connection on a manager, as ``text/event-stream`` chunks.

    Replay first, per source, up to the boundary each source stood at when the
    subscriber registered; then the queue. One ``desync`` — the manager's own — when
    any source's part could not be honoured (R2.8).
    """
    delivered = 0
    reason = "client"
    try:
        boundary = broker.offsets()
        replay: List[Frame] = []
        desync = ""
        if cursor is not None:
            if cursor.desync:
                desync = cursor.desync
            else:
                for name, offset in cursor.offsets.items():
                    if name == broker.own_name:
                        end = boundary.get(name, 0)
                        if offset > end:
                            desync = "truncated"
                            break
                        if end - offset > REPLAY_BYTES:
                            desync = "replay-window"
                            break
                        for record in LogTail(broker.log_path, offset=offset).read():
                            if record.cursor > end:
                                break
                            replay.append(
                                Frame(
                                    kind="log",
                                    data=dict(record.data, instance=broker.own_name),
                                    cursor=record.cursor,
                                )
                            )
                        continue
                    if broker.fleet.config.member(name) is None:
                        continue  # no longer registered: dropped
                    try:
                        replay.extend(
                            await asyncio.get_event_loop().run_in_executor(
                                None,
                                lambda n=name, o=offset: list(
                                    _replay_member(broker, n, o, boundary.get(n))
                                ),
                            )
                        )
                    except _Resync as exc:
                        desync = exc.reason
                        break
                    except Exception as exc:  # noqa: BLE001 — a member that will not replay
                        logger.warning("%s could not replay: %s", name, exc)
                        desync = "member"
                        break
        if desync:
            eventlog.emit("stream.desync", reason=desync, cursor=str(cursor))
            yield encode_frame(
                Frame(
                    kind="desync",
                    data={
                        "reason": desync,
                        "cursor": encode_cursor(cursor.offsets) if cursor else None,
                    },
                )
            )
            replay = []
        yield f"retry: {RETRY_MS}\n\n"
        # Each replayed frame carries the position AFTER it, per source: the sources
        # not yet replayed keep the client's own offsets, so a drop mid-replay resumes
        # exactly there rather than at the boundary (which would skip the rest).
        progress = dict(boundary)
        if cursor is not None and not cursor.desync:
            for name, offset in cursor.offsets.items():
                if name in progress:
                    progress[name] = min(offset, progress[name])
        for frame in replay:
            source = str(frame.data.get("instance") or broker.own_name)
            if isinstance(frame.cursor, int):
                progress[source] = frame.cursor
            if matches(frame.data, subscriber.work_items):
                delivered += 1
                yield encode_frame(
                    Frame(
                        kind=frame.kind, data=frame.data, cursor=encode_cursor(progress)
                    )
                )

        last_keepalive = _loop_time()
        while True:
            try:
                frame = await asyncio.wait_for(
                    subscriber.queue.get(), timeout=TICK_SECONDS
                )
            except asyncio.TimeoutError:
                frame = None
            if frame is not None:
                delivered += 1
                yield encode_frame(frame)
                continue
            now = _loop_time()
            if now - last_keepalive >= keep_alive:
                last_keepalive = now
                yield keepalive()
    except asyncio.CancelledError:
        reason = "shutdown"
        raise
    finally:
        broker.unsubscribe(subscriber)
        eventlog.emit("stream.disconnected", frames=delivered, reason=reason)


def _loop_time() -> float:
    return asyncio.get_event_loop().time()
