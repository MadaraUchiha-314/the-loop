"""The outbox — the events no channel accepted, kept until one does (issue-409).

``publish`` records an event on the ledger and then fans it out, best-effort per
channel. Before this module the fan-out's failure was **thrown away**: one
``channel.post_failed`` line, one ``bus.published`` line with ``posted: 0`` at
debug level, and nothing anywhere that remembered the event still needed
delivering. A rotated token, a renamed channel or a rate limit therefore cost the
message — and the loudest case is ``session.awaiting_input``, where the message is
a question a session is now blocked on.

So the bus writes what nobody took to ``<state.root>/channels/undelivered.json``
and each daemon drains it:

* :func:`remember` — called by the bus when **at least one channel was asked and
  none accepted**. Never raises: an outbox that cannot be written degrades to the
  behaviour it replaces.
* :func:`drain` — claim the due entries under the lock, post them outside it, then
  remove what landed. It **only posts**: a drained entry never reaches the ledger,
  so a replay can never write a comment, open an issue or answer a gate.
* :func:`start_drainer` — the daemons' hook, shaped exactly like
  :func:`the_loop.channels.watcher.start_watcher`: a daemon thread looping
  ``stop_event.wait(interval)``, a raising cycle logged and survived.
* :func:`summary` — what ``the-loop status`` prints while the backlog is non-empty.

Bounded on three axes, because the recovery path must not become the next
outage: :data:`OUTBOX_CAP` entries at rest, :data:`DRAIN_BUDGET` posts per cycle,
and a per-entry backoff doubling from :data:`RETRY_BASE_SECONDS` to
:data:`RETRY_MAX_SECONDS`.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from .. import eventlog, runlock
from ..identity import Principal
from .base import Channel, ChannelError, Event, PostResult

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "DRAIN_BUDGET",
    "DRAIN_INTERVAL_SECONDS",
    "OUTBOX_CAP",
    "RETRY_BASE_SECONDS",
    "RETRY_MAX_SECONDS",
    "drain",
    "entries",
    "path_for",
    "remember",
    "start_drainer",
    "summary",
]

#: How many undelivered events one deployment keeps. Past the cap the OLDEST goes,
#: with a warning: the alternative is a file that grows for as long as the outage
#: lasts, holding message text nobody will ever read back.
OUTBOX_CAP = 200

#: How many entries one drain cycle posts. The backlog is drained oldest first, so
#: a budget spreads a large one over several cycles instead of opening two hundred
#: connections to a provider that may be the thing that is failing.
DRAIN_BUDGET = 20

#: How often each daemon's drainer wakes. Slower than a poll cycle on purpose —
#: nothing here is time-critical past "sooner than the operator notices".
DRAIN_INTERVAL_SECONDS = 60

#: The first wait after a failed attempt; it doubles per attempt up to
#: :data:`RETRY_MAX_SECONDS`. A rate limit and a rotated token both resolve in
#: minutes-to-hours, and neither is helped by a tighter loop.
RETRY_BASE_SECONDS = 60
RETRY_MAX_SECONDS = 3600

_LOCK_WARNED = False


def path_for(cli_config: Optional[Mapping[str, Any]]) -> Path:
    """Where this deployment's backlog lives — ``<root>/channels/undelivered.json``."""
    from ..state import layout_from_config

    return Path(layout_from_config(dict(cli_config or {})).channels_outbox)


# -- writing (R1) ---------------------------------------------------------------------


def remember(
    event: Event,
    posts: Sequence[PostResult],
    cli_config: Optional[Mapping[str, Any]],
) -> bool:
    """Queue ``event`` for redelivery; ``True`` when it was written.

    The caller has already established the only condition that matters — at least
    one channel was asked and none accepted — so this does not re-judge it. It
    emits ``channel.undelivered`` itself, at warning, because the fact is worth
    a line in whichever process published (R4.1).
    """
    path = path_for(cli_config)
    entry = {
        "at": _now(),
        "attempts": 0,
        "lastAttemptAt": "",
        "lastError": _first_error(posts),
        "channels": [post.channel for post in posts],
        "event": _event_payload(event),
    }
    try:
        with _locked(path) as book:
            book[_new_id()] = entry
            dropped = _evict(book)
            _save(path, book)
            depth = len(book)
    except Exception:  # noqa: BLE001 — a failed queue never breaks a publish (R1.6)
        logger.exception("could not queue an undelivered %s", event.event_type)
        return False
    for name, lost in dropped:
        eventlog.emit(
            "channel.undelivered_dropped",
            level="warning",
            work_item=lost.get("workItem") or None,
            event_type=lost.get("eventType") or None,
            queued_at=name,
            cap=OUTBOX_CAP,
        )
    eventlog.emit(
        "channel.undelivered",
        level="warning",
        work_item=event.work_item or None,
        event_type=event.event_type,
        channels=[post.channel for post in posts],
        error=entry["lastError"] or None,
        pending=depth,
    )
    return True


def entries(cli_config: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """The backlog, oldest first, each entry carrying its ``id``. Never raises."""
    try:
        book = _load(path_for(cli_config))
    except Exception:  # noqa: BLE001 — an unreadable backlog reads as no backlog
        logger.debug("could not read the undelivered outbox", exc_info=True)
        return []
    return [dict(record, id=key) for key, record in book.items()]


def summary(cli_config: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """What ``the-loop status`` reports about delivery (R3).

    ``{"pending": 0, …}`` for an empty, absent or unreadable file — a backlog
    nobody can read is not a backlog anyone can act on, and `status` must still
    answer its own question (R3.4).
    """
    queued = entries(cli_config)
    if not queued:
        return {"pending": 0, "oldest": "", "waitedSeconds": 0, "lastError": ""}
    oldest = str(queued[0].get("at") or "")
    newest = queued[-1]
    return {
        "pending": len(queued),
        "oldest": oldest,
        "waitedSeconds": _age_seconds(oldest),
        "lastError": str(newest.get("lastError") or ""),
        "channels": sorted(
            {
                str(name)
                for record in queued
                for name in (record.get("channels") or [])
                if name
            }
        ),
    }


# -- draining (R2) --------------------------------------------------------------------


def drain(
    cli_config: Optional[Mapping[str, Any]],
    *,
    channels: Optional[Sequence[Channel]] = None,
    budget: int = DRAIN_BUDGET,
    now: Optional[datetime] = None,
) -> Dict[str, int]:
    """Post as much of the backlog as is due; return what the cycle did.

    Claim, post, settle — in three steps, because posting takes a network call and
    the file's lock must not be held across it: the due entries are stamped with
    an attempt **under the lock** (so a second drainer skips them), posted outside
    it, and the delivered ones removed under the lock again.
    """
    path = path_for(cli_config)
    moment = now or _utcnow()
    try:
        with _locked(path) as book:
            if not book:
                return {"attempted": 0, "delivered": 0, "pending": 0}
            due = [key for key, record in book.items() if _due(record, moment)][:budget]
            for key in due:
                record = book[key]
                record["attempts"] = int(record.get("attempts") or 0) + 1
                record["lastAttemptAt"] = _stamp(moment)
            claimed = [(key, dict(book[key])) for key in due]
            if due:
                _save(path, book)
            pending = len(book)
    except Exception:  # noqa: BLE001 — a drain never takes its daemon with it
        logger.exception("could not claim undelivered events")
        return {"attempted": 0, "delivered": 0, "pending": 0}
    if not claimed:
        return {"attempted": 0, "delivered": 0, "pending": pending}

    resolved = list(channels) if channels is not None else _channels(cli_config)
    done: List[str] = []  # ids to remove: delivered, or unreadable
    failed: Dict[str, str] = {}  # id -> the error to remember
    delivered = 0
    for key, record in claimed:
        event = _event_from(record.get("event") or {})
        if event is None:
            # A record this CLI cannot read is dropped rather than retried
            # forever; whatever the ledger recorded still stands on the ticket.
            logger.warning("dropping an unreadable outbox entry %s", key)
            done.append(key)
            continue
        ok, error = _post(event, resolved)
        if not ok:
            failed[key] = error
            continue
        done.append(key)
        delivered += 1
        eventlog.emit(
            "channel.delivered_late",
            work_item=event.work_item or None,
            event_type=event.event_type,
            attempts=record.get("attempts"),
            waited_seconds=_age_seconds(str(record.get("at") or "")),
        )

    try:
        with _locked(path) as book:
            for key in done:
                book.pop(key, None)
            for key, error in failed.items():
                if key in book:
                    book[key]["lastError"] = error
            _save(path, book)
            pending = len(book)
    except Exception:  # noqa: BLE001 — as above; the next cycle re-reads the file
        logger.exception("could not settle a drained batch")
    return {"attempted": len(claimed), "delivered": delivered, "pending": pending}


def start_drainer(
    cli_config: Optional[Mapping[str, Any]],
    stop_event: threading.Event,
    *,
    interval_override: Optional[float] = None,
) -> Optional[threading.Thread]:
    """A background drainer, or ``None`` when this deployment has no channels.

    :func:`the_loop.channels.watcher.start_watcher`'s shape exactly: a daemon
    thread ending on the caller's stop event, a failing cycle logged and survived
    (R2.6). Both daemons start one — either may be the only one running — and two
    drainers are safe, because a cycle claims its entries under the file's lock.
    """
    if not (cli_config or {}).get("channels"):
        return None
    interval = (
        interval_override if interval_override is not None else DRAIN_INTERVAL_SECONDS
    )
    frozen_config = dict(cli_config or {})

    def run() -> None:
        while not stop_event.wait(interval):
            try:
                drain(frozen_config)
            except Exception:  # noqa: BLE001 — never kill a daemon over a channel
                logger.exception("channel drain cycle raised; continuing")

    thread = threading.Thread(target=run, name="the-loop-outbox", daemon=True)
    thread.start()
    logger.debug("channels: draining undelivered events every %ss", interval)
    return thread


def _channels(cli_config: Optional[Mapping[str, Any]]) -> List[Channel]:
    from .base import load_channels

    try:
        return list(load_channels(dict(cli_config or {})))
    except Exception:  # noqa: BLE001 — a broken channel config drains nothing
        logger.exception("could not load the channels to drain into")
        return []


def _post(event: Event, channels: Sequence[Channel]) -> Tuple[bool, str]:
    """Re-post one event to every channel that should have had it (R2.4).

    The same two rules ``publish``'s fan-out applies — never back to the event's
    own source, only where it is subscribed — and never the ledger: this path
    posts, it does not record.
    """
    delivered, error = False, ""
    for channel in channels:
        if channel.name == event.source or not channel.subscribes(event.event_type):
            continue
        try:
            result = channel.post(event)
        except ChannelError as exc:
            result = PostResult(channel=channel.name, ok=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001 — a provider bug is this entry's
            logger.exception("channel %s post raised while draining", channel.name)
            result = PostResult(channel=channel.name, ok=False, error=str(exc))
        if result.ok:
            delivered = True
            eventlog.emit(
                "channel.posted",
                channel=result.channel,
                work_item=event.work_item,
                event_type=event.event_type,
                thread=result.thread or None,
            )
        elif not error:
            error = result.error or f"{channel.name}: refused"
    return delivered, error or "no channel took it"


def _due(record: Mapping[str, Any], now: datetime) -> bool:
    """Whether this entry's backoff has elapsed — a first attempt always has."""
    attempts = _int(record.get("attempts"))
    last = _parse(str(record.get("lastAttemptAt") or ""))
    if not attempts or last is None:
        return True
    wait = min(RETRY_BASE_SECONDS * (2 ** (attempts - 1)), RETRY_MAX_SECONDS)
    return (now - last).total_seconds() >= wait


# -- the file -------------------------------------------------------------------------


def _load(path: Path) -> Dict[str, Dict[str, Any]]:
    """The file as ``{id: entry}``; ``{}`` for an absent or unusable one.

    Every field is coerced on the way in, the rule ``channels/state.py`` follows:
    a file written by another version loads with what it has, because the worst a
    partial entry can cost is one message posted without its detail — and raising
    here would cost every message.
    """
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(
            "undelivered outbox %s is unreadable (%s); treating it as empty", path, exc
        )
        return {}
    pending = raw.get("pending") if isinstance(raw, Mapping) else None
    if not isinstance(pending, Mapping):
        return {}
    book: Dict[str, Dict[str, Any]] = {}
    for key, value in pending.items():
        if isinstance(key, str) and isinstance(value, Mapping):
            book[key] = _entry(value)
    return dict(sorted(book.items()))  # the id sorts by the time it was queued


def _entry(record: Mapping[str, Any]) -> Dict[str, Any]:
    raw = record.get("channels")
    return {
        "at": str(record.get("at") or ""),
        "attempts": _int(record.get("attempts")),
        "lastAttemptAt": str(record.get("lastAttemptAt") or ""),
        "lastError": str(record.get("lastError") or ""),
        "channels": (
            [str(name) for name in raw if name]
            if isinstance(raw, (list, tuple))
            else []
        ),
        "event": dict(record.get("event") or {}),
    }


def _save(path: Path, book: Mapping[str, Mapping[str, Any]]) -> None:
    """Atomic write (tmp + rename), the channel state's idiom exactly."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"version": 1, "pending": dict(book)}, indent=2)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("could not write the undelivered outbox %s: %s", path, exc)
        try:
            os.unlink(tmp)
        except OSError:
            pass


@contextmanager
def _locked(path: Path) -> Iterator[Dict[str, Dict[str, Any]]]:
    """Load ``path`` under an exclusive lock held until the block ends.

    ``ChannelState.locked``'s contract, on ``<path>.lock`` for the same reason:
    the atomic save would release a lock taken on the file itself. Without
    ``flock`` the read-modify-write runs unlocked and says so once, at debug.
    """
    global _LOCK_WARNED
    if not runlock.HAVE_FLOCK:
        if not _LOCK_WARNED:
            logger.debug(
                "undelivered outbox %s: no flock on this platform — read-modify-"
                "write runs unlocked",
                path,
            )
            _LOCK_WARNED = True
        yield _load(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(str(path) + ".lock", os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    try:
        runlock.fcntl.flock(lock_fd, runlock.fcntl.LOCK_EX)
        yield _load(path)
    finally:
        try:
            runlock.fcntl.flock(lock_fd, runlock.fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def _evict(book: Dict[str, Dict[str, Any]]) -> List[Tuple[str, Dict[str, str]]]:
    """Drop the oldest entries past the cap; return what went, for the log."""
    dropped: List[Tuple[str, Dict[str, str]]] = []
    while len(book) > OUTBOX_CAP:
        key = next(iter(book))
        lost = book.pop(key)
        event = lost.get("event") or {}
        dropped.append(
            (
                str(lost.get("at") or key),
                {
                    "workItem": str(event.get("workItem") or ""),
                    "eventType": str(event.get("eventType") or ""),
                },
            )
        )
    return dropped


# -- the event, to disk and back ------------------------------------------------------


def _event_payload(event: Event) -> Dict[str, Any]:
    """One :class:`Event` as JSON — field by field, never pickled."""
    return {
        "eventType": event.event_type,
        "workItem": event.work_item,
        "text": event.text,
        "url": event.url,
        "detail": {str(k): str(v) for k, v in dict(event.detail or {}).items()},
        "source": event.source,
        "summary": event.summary,
        "actor": (
            {"ids": event.actor.to_dict(), "name": event.actor.name}
            if event.actor
            else {}
        ),
    }


def _event_from(payload: Mapping[str, Any]) -> Optional[Event]:
    """The event back, or ``None`` when the entry names no type to publish."""
    event_type = str(payload.get("eventType") or "")
    if not event_type:
        return None
    detail_raw = payload.get("detail")
    detail = (
        {str(k): str(v) for k, v in detail_raw.items()}
        if isinstance(detail_raw, Mapping)
        else {}
    )
    return Event(
        event_type=event_type,
        work_item=str(payload.get("workItem") or ""),
        text=str(payload.get("text") or ""),
        url=str(payload.get("url") or ""),
        detail=detail,
        source=str(payload.get("source") or "loop"),
        actor=_actor_from(payload.get("actor")),
        summary=str(payload.get("summary") or ""),
    )


def _actor_from(raw: Any) -> Optional[Principal]:
    if not isinstance(raw, Mapping):
        return None
    ids_raw = raw.get("ids")
    ids = (
        {str(k): str(v) for k, v in ids_raw.items() if v}
        if isinstance(ids_raw, Mapping)
        else {}
    )
    name = str(raw.get("name") or "")
    return Principal(ids=ids, name=name) if (ids or name) else None


# -- small helpers --------------------------------------------------------------------


def _new_id() -> str:
    """Sortable by the moment it was queued, unique across the processes sharing
    the file: a fixed-width microsecond stamp orders the backlog — oldest first is
    the order a drain honours and the cap evicts by — and the suffix keeps two
    writers in the same microsecond apart."""
    return f"{_utcnow().strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid.uuid4().hex[:8]}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now() -> str:
    return _stamp(_utcnow())


def _parse(stamp: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _age_seconds(stamp: str) -> int:
    moment = _parse(stamp)
    if moment is None:
        return 0
    return max(0, int((_utcnow() - moment).total_seconds()))


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _first_error(posts: Sequence[PostResult]) -> str:
    """The first refusal, channel-prefixed — but never twice: a provider that
    already names itself in its message reads badly with the name in front."""
    for post in posts:
        if not post.ok and post.error:
            error = post.error.strip()
            prefix = f"{post.channel}:"
            return error if error.startswith(prefix) else f"{post.channel}: {error}"
    return ""
