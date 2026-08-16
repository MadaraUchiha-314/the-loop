"""The server-push stream behind ``GET /api/v1/stream`` (issue-239).

The control plane used to learn nothing until it asked again: every screen was driven by
a two-round poll on a fixed timer, so an operator watching an agent work saw each turn up
to 15 seconds late, and looking sooner cost the whole board. This module is the other
direction — the service tells the browser what changed, and the browser refreshes only
what that change touches.

**Server-Sent Events, not WebSocket** (design.md §Trade-offs). The deciding reason is not
ergonomics: a WebSocket handshake is exempt from CORS, so it would need a hand-written
``Origin`` check to recover a boundary an ordinary ``GET`` inherits from the middleware
``service.cors`` already installs. SSE also brings ``Last-Event-ID`` resume and browser
reconnection for free, needs no dependency beyond Starlette, and gives up only
bidirectionality — which nothing here wants, because replies already have a route.

**One tailer, many subscribers.** Several processes append to the event log (the poller,
the webhook receiver, the harness, the ``sessions`` CLI, this service), so the file is the
only place all of them meet — decision-025 — and an in-process bus would see a fraction of
the traffic. :class:`StreamBroker` runs one task that reads the file once per tick and
fans out into a bounded queue per subscriber, so N subscribers cost one read, and a
browser that stops reading harms only itself.

**The stream never carries ``api.request`` or ``mcp.call``.** Every route emits
``api.request``. A stream that delivered it would feed itself: the control plane's own
refresh produces API requests, which produce events, which produce frames, which trigger
another refresh — a loop that never idles and gets worse the more people watch. The
exclusion lives in :class:`LogTail`, the narrowest point every frame passes through, and
there is deliberately **no opt-in flag**; a flag would be a documented way to build the
loop, and ``GET /api/v1/events`` still serves those records to anyone who wants them.

Spec: docs/specs/issue-239/  ·  Requirements R1, R2, R5
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Set, Tuple, Union

logger = logging.getLogger("the-loop.service")

__all__ = [
    "REPLAY_BYTES",
    "TICK_SECONDS",
    "QUEUE_SIZE",
    "EXCLUDED_EVENTS",
    "Frame",
    "LogTail",
    "Record",
    "StreamBroker",
    "Subscriber",
    "RETRY_MS",
    "encode_frame",
    "parse_cursor",
    "resolve_cursor",
    "serve",
]

#: How far back a reconnecting subscriber may replay. A cursor further behind than
#: this resolves to a ``desync`` rather than an unbounded read of history
#: (requirements abuse case 4). 256 KiB is a few thousand event records — far more
#: than a browser misses across a reconnect, and a bounded amount of work.
REPLAY_BYTES = 256 * 1024

#: Seconds between reads of the event log. Requirements R1.2 allows 2s end to end;
#: at 0.5s the tail contributes a quarter of that and costs two ``stat`` calls a
#: second, whoever is connected.
TICK_SECONDS = 0.5

#: Frames held for one subscriber before it is considered too slow to keep up.
#: The bound is what makes memory per subscriber a constant rather than a function
#: of the client's appetite (abuse case 5).
QUEUE_SIZE = 256

#: How often an unresolvable transcript path is retried, in ticks. A session
#: registers after its work item does, so "no transcript yet" is a normal state
#: that fixes itself — without this the client would have to reconnect to notice.
_TRANSCRIPT_RETRY_TICKS = 10

#: What ``retry:`` tells ``EventSource`` to wait before reconnecting, in
#: milliseconds. The browser's own default is unspecified and has been as low as
#: 500ms; three seconds is long enough that a service restart is one reconnect
#: rather than six.
RETRY_MS = 3000

#: Event types the stream never carries. See the module docstring: this is a
#: correctness property of the whole design, not a preference, which is why it
#: sits at the tailer and has no configuration.
EXCLUDED_EVENTS = frozenset({"api.request", "mcp.call"})


# -- records and frames ---------------------------------------------------------


@dataclass(frozen=True)
class Record:
    """One event-log record, with the offset **after** it as its cursor.

    After, not before, so a client that reconnects quoting a record's cursor is
    served what came next rather than the record it already has.
    """

    data: Dict[str, Any]
    cursor: int


@dataclass(frozen=True)
class Frame:
    """One SSE frame. ``kind`` becomes the ``event:`` field, ``data`` the payload."""

    kind: str
    data: Dict[str, Any]
    cursor: Optional[int] = None


def encode_frame(frame: Frame) -> str:
    """Serialize one frame in the ``text/event-stream`` wire format.

    ``json.dumps`` cannot emit a bare newline inside a string, so the payload is
    always one ``data:`` line — which is what lets the client parse a frame
    without reassembling continuations.
    """
    lines: List[str] = []
    if frame.cursor is not None:
        lines.append(f"id: {frame.cursor}")
    lines.append(f"event: {frame.kind}")
    lines.append(f"data: {json.dumps(frame.data, separators=(',', ':'), default=str)}")
    return "\n".join(lines) + "\n\n"


def keepalive() -> str:
    """An SSE comment. Two bytes of payload that stop an intermediary reaping an
    idle connection, and let the client tell "quiet" from "dead" (R1.4)."""
    return ": keep-alive\n\n"


# -- the cursor -----------------------------------------------------------------


def parse_cursor(raw: Optional[str]) -> Optional[int]:
    """``Last-Event-ID`` as an offset, or ``None`` when the client sent none.

    Raises :class:`ValueError` for anything else — including the empty string and
    a negative number. Refusing is the point (abuse case 3): a malformed cursor
    that fell back to "from the beginning" would turn a typo into the unbounded
    read :data:`REPLAY_BYTES` exists to prevent.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text.isdigit():
        raise ValueError(
            f"Last-Event-ID must be a non-negative integer byte offset, got {raw!r}"
        )
    return int(text)


def resolve_cursor(cursor: Optional[int], size: int) -> Tuple[int, str]:
    """Where to start reading, and the ``desync`` reason if the ask was refused.

    Three answers, and the client's correct response to the last two is identical
    — refetch everything — which is why they share one frame kind:

    * ``(cursor, "")`` — inside the replay window; replay from there.
    * ``(size, "truncated")`` — the offset is past the end, so the file was
      truncated or rotated under the service and that offset means nothing now.
    * ``(size, "replay-window")`` — further behind than :data:`REPLAY_BYTES`.

    A first connection (``cursor is None``) starts at the end: a new subscriber
    wants what happens next, and the board it just rendered is the history.
    """
    if cursor is None:
        return size, ""
    if cursor > size:
        return size, "truncated"
    if size - cursor > REPLAY_BYTES:
        return size, "replay-window"
    return cursor, ""


# -- the tailer -----------------------------------------------------------------


class LogTail:
    """Reads whole JSONL records from an append-only file, from an offset.

    Deliberately not built on :func:`the_loop.eventlog.read_events`: that reader
    opens the file and consumes it whole, which is right for a query and wrong for
    a tail that must resume mid-file and survive a partial write. The two share the
    tolerance that matters — a corrupt line is skipped, a missing file reads as
    empty — because both are reading a file several processes are appending to.
    """

    def __init__(self, path: Union[str, Path], offset: int = 0):
        self.path = Path(path)
        self.offset = int(offset)
        self._partial = b""

    def size(self) -> int:
        """The file's current size, or 0 while it does not exist yet."""
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def seek_to_end(self) -> int:
        self.offset = self.size()
        self._partial = b""
        return self.offset

    def read(self) -> Iterator[Record]:
        """Every whole record appended since the last read.

        **Bytes, not text.** The cursor is a byte offset the client quotes back as
        ``Last-Event-ID``, so every length here has to be the length the filesystem
        agrees with. Decoding first and measuring after would make the arithmetic
        depend on how the decoder handled a half-written multi-byte character — an
        off-by-a-few that only shows up on a log with non-ASCII in it, which every
        real transcript comment has.

        A trailing fragment is held in ``_partial`` rather than emitted or dropped:
        several processes append to this file, so a read can land mid-write, and
        both alternatives are wrong — emitting puts malformed JSON on the wire,
        dropping loses the record once it completes.

        The offset advances past **every** record, including an excluded one, or a
        log full of ``api.request`` would be re-read on every tick forever.
        """
        size = self.size()
        if size < self.offset:
            # Truncated or rotated under us. Start again from the top rather than
            # reading from an offset that now means something else entirely.
            self.offset = 0
            self._partial = b""
        if size == self.offset:
            return
        try:
            with open(self.path, "rb") as handle:
                handle.seek(self.offset)
                chunk = handle.read()
        except OSError:  # removed between the stat and the open
            return
        self.offset += len(chunk)

        buffer = self._partial + chunk
        lines = buffer.split(b"\n")
        # `split` always leaves a last element: "" when the buffer ended on a
        # newline, the incomplete record otherwise. Either way it is what carries
        # over, and every other element is a whole line.
        self._partial = lines.pop()

        cursor = self.offset - len(buffer)  # absolute offset of buffer[0]
        for raw in lines:
            cursor += len(raw) + 1  # the record, plus the newline that ended it
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except ValueError:
                continue  # a corrupt or half-flushed line, as `eventlog` tolerates
            if not isinstance(data, dict):
                continue
            if str(data.get("event", "")) in EXCLUDED_EVENTS:
                continue
            yield Record(data=data, cursor=cursor)


def matches(record: Dict[str, Any], work_items: Sequence[str]) -> bool:
    """Whether a record passes a subscriber's work-item filter.

    An empty filter matches everything — that is the board's subscription. The
    two-field check mirrors :func:`the_loop.eventlog._matches_work_item`: routing
    events name several work items at once, and a filter that only read
    ``work_item`` would silently drop them.
    """
    if not work_items:
        return True
    if record.get("work_item") in work_items:
        return True
    return any(ref in (record.get("work_items") or []) for ref in work_items)


# -- the broker -----------------------------------------------------------------


@dataclass(eq=False)
class Subscriber:
    """One open connection: what it asked for, and what is waiting for it.

    ``eq=False`` on purpose — a subscriber is an **identity**, not a value. Two
    browser tabs watching the same work item ask for exactly the same thing, and
    field-wise equality would make the registry collapse them into one and
    unsubscribing either close both.
    """

    queue: "asyncio.Queue[Frame]"
    work_items: List[str] = field(default_factory=list)
    transcripts: List[str] = field(default_factory=list)
    frames: int = 0
    #: Set once the subscriber has been told to resynchronise, so a queue that
    #: stays full does not enqueue a second desync behind the first.
    desynced: bool = False

    def offer(self, frame: Frame) -> bool:
        """Enqueue, or drain and desync. ``True`` when the frame itself was taken.

        A slow reader is dropped *to a resync*, not disconnected: the connection is
        still useful, and one ``desync`` frame is a smaller, bounded promise than an
        unbounded backlog. Memory per subscriber stays :data:`QUEUE_SIZE` frames
        whatever the client does (abuse case 5).
        """
        try:
            self.queue.put_nowait(frame)
            self.frames += 1
            return True
        except asyncio.QueueFull:
            if self.desynced:
                return False
            while not self.queue.empty():
                self.queue.get_nowait()
            self.desynced = True
            self.queue.put_nowait(
                Frame(kind="desync", data={"reason": "queue-overflow"})
            )
            return False


class StreamBroker:
    """One tailer task; one bounded queue per subscriber.

    The capacity check happens at :meth:`subscribe`, before any queue, task or file
    handle exists, so a refused connection costs one rejected request (abuse case
    1). The task starts with the first subscriber and stops with the last: a
    service nobody is watching does no work.
    """

    def __init__(
        self,
        log_path: Union[str, Path],
        max_subscribers: int,
        transcript_path=None,
    ):
        self.log_path = Path(log_path)
        self.max_subscribers = max(1, int(max_subscribers))
        #: Injected so the broker does not import the session registry, and so the
        #: transcript watch is testable without one. Takes a ref, returns a path or
        #: ``None`` while the session has not registered a conversation yet.
        self._transcript_path = transcript_path
        self._subscribers: Set[Subscriber] = set()
        self._task: Optional[asyncio.Task] = None
        self._tail = LogTail(self.log_path)
        self._sizes: Dict[str, int] = {}
        self._ticks = 0

    # -- lifecycle --------------------------------------------------------------

    def tail_size(self) -> int:
        """The event log's current size — where a fresh subscriber starts."""
        return self._tail.size()

    @property
    def count(self) -> int:
        return len(self._subscribers)

    @property
    def at_capacity(self) -> bool:
        return self.count >= self.max_subscribers

    def subscribe(
        self, work_items: Sequence[str] = (), transcripts: Sequence[str] = ()
    ) -> Subscriber:
        """Register a subscriber, or raise if the service is at capacity."""
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
        self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.discard(subscriber)
        if not self._subscribers:
            self.stop()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._tail.seek_to_end()
            self._task = asyncio.ensure_future(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    # -- the tick ---------------------------------------------------------------

    async def _run(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:  # noqa: BLE001 — o11y must never kill the tailer
                logger.exception("stream tailer tick failed; continuing")
            await asyncio.sleep(TICK_SECONDS)

    def tick(self) -> None:
        """Read the log once, stat the watched transcripts, fan out to everyone."""
        self._ticks += 1
        for record in self._tail.read():
            frame = Frame(kind="log", data=record.data, cursor=record.cursor)
            for subscriber in list(self._subscribers):
                if matches(record.data, subscriber.work_items):
                    subscriber.offer(frame)
        self._tick_transcripts()

    def _tick_transcripts(self) -> None:
        """Notify on growth of the transcripts subscribers asked to watch.

        The frame carries a line count and no content: the client then calls
        ``GET /api/v1/sessions/transcript``, which owns the path validation and the
        fail-closed rules (issue-209). Duplicating that boundary here would be a
        second place to get it wrong.
        """
        if self._transcript_path is None:
            return
        watched = {ref for s in self._subscribers for ref in s.transcripts}
        for ref in watched:
            known = self._sizes.get(ref)
            if known is None and self._ticks % _TRANSCRIPT_RETRY_TICKS not in (0, 1):
                # Not resolved yet — retry occasionally rather than every tick, so
                # a work item with no session does not stat a path per half-second.
                continue
            try:
                path = self._transcript_path(ref)
            except Exception:  # noqa: BLE001 — an unresolvable ref is a normal state
                path = None
            if not path:
                continue
            try:
                size = os.path.getsize(path)
                lines = _count_lines(path)
            except OSError:
                continue
            if known is not None and size == known:
                continue
            self._sizes[ref] = size
            if known is None:
                continue  # first sighting establishes the baseline, not a change
            frame = Frame(kind="transcript", data={"ref": ref, "totalLines": lines})
            for subscriber in list(self._subscribers):
                if ref in subscriber.transcripts:
                    subscriber.offer(frame)


async def serve(
    broker: StreamBroker,
    subscriber: Subscriber,
    cursor: Optional[int] = None,
    keep_alive: int = 15,
):
    """One subscriber's connection, as ``text/event-stream`` chunks.

    The order is deliberate. Replay is resolved and sent **first**, from the
    broker's own tail, before the subscriber is fed live frames — so a reconnect
    cannot interleave history with what arrives while it is catching up. The
    broker's tailer only then starts (if it is not already running), positioned at
    the end of the log.

    **Disconnect is Starlette's to detect, not ours.** ``StreamingResponse`` runs
    ``listen_for_disconnect`` alongside this generator and cancels it when the
    client goes away — the cancellation arrives here as :class:`asyncio.
    CancelledError`, and the ``finally`` releases the slot. An earlier draft also
    polled ``Request.is_disconnected`` from inside the loop; that reads the same
    ASGI ``receive`` channel Starlette is already consuming, and two consumers of
    one channel is a race waiting for a slow week. Removed rather than made to
    work: there is nothing it could tell us that the cancellation does not.

    The loop is a bounded wait rather than a blocking ``get`` because the
    keep-alive has to go out on a schedule that does not depend on traffic
    arriving.
    """
    delivered = 0
    reason = "client"
    try:
        size = broker.tail_size()
        start, desync = resolve_cursor(cursor, size)
        if desync:
            from .. import eventlog

            eventlog.emit("stream.desync", reason=desync, cursor=cursor)
            yield encode_frame(
                Frame(kind="desync", data={"reason": desync, "cursor": cursor})
            )
        # `retry:` sets EventSource's own reconnect delay. Sent once, before
        # anything else, so a connection that drops immediately still got it.
        yield f"retry: {RETRY_MS}\n\n"

        for record in LogTail(broker.log_path, offset=start).read():
            if matches(record.data, subscriber.work_items):
                delivered += 1
                yield encode_frame(
                    Frame(kind="log", data=record.data, cursor=record.cursor)
                )

        broker.start()

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
    except asyncio.CancelledError:  # the server is going down
        reason = "shutdown"
        raise
    finally:
        broker.unsubscribe(subscriber)
        from .. import eventlog

        eventlog.emit("stream.disconnected", frames=delivered, reason=reason)


def _loop_time() -> float:
    return asyncio.get_event_loop().time()


def _count_lines(path: Union[str, Path]) -> int:
    try:
        with open(path, "rb") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0
