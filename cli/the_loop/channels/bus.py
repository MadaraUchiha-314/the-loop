"""The event bus — the one caller of every channel (issue-309, decision-103).

``publish`` does exactly R1.4, in order:

1. **Record.** When the catalog says the event is recorded and it did not originate
   on the ledger, the ledger writes it down first — a comment with an envelope, or
   the issue itself for ``work-item.create``. The record's URL is carried onto the
   event so subscribers can link to it.
2. **Fan out.** Every enabled channel that subscribes to the type and is not the
   event's source posts it, rendering it itself.

Best-effort per channel, always: a failing ledger or channel is a ``PostResult`` and
an event-log line, never an exception to the publisher — the caller decides what a
failed record means to *it* (the ask's exit code still says the post failed; a
reply's pipeline still delivers).

3. **Queue what nobody took.** When at least one channel was asked and every one of
   them refused, the event goes to :mod:`the_loop.channels.outbox` and a warning
   says so, so a rotated token or a rate limit costs a delay rather than the
   message (issue-409). Best-effort like everything else here: the
   ``PublishResult`` the caller sees is the same either way.

``broadcast`` is the pre-issue-309 spelling, kept as a wrapper that never records.

``open_conversation`` (issue-317) is the bus's other verb: not an event, an
**operation** — ask every enabled channel that has a conversation to open (a
Slack thread; the ledger has none, the issue *is* its conversation) to open the
work item's, now. The dispatcher calls it on the spawn path, so the thread exists
the moment a start is accepted rather than when the first event arrives. Same
contract as ``publish``: best-effort per channel, a failure is a ``PostResult``
and a ``channel.open_failed`` line, never an exception to the caller.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Callable, List, Mapping, Optional, Sequence

from .. import eventlog
from .base import (
    Channel,
    ChannelError,
    Conversational,
    Event,
    Ledger,
    PostResult,
    PublishResult,
    load_channels,
    load_ledger,
)
from .events import is_recorded

logger = logging.getLogger("the-loop.channels")

__all__ = ["broadcast", "open_conversation", "publish"]


def publish(
    event: Event,
    cli_config: Optional[Mapping[str, Any]] = None,
    *,
    channels: Optional[Sequence[Channel]] = None,
    client_factory: Optional[Callable] = None,
    record: Optional[bool] = None,
    ledger: Optional[Ledger] = None,
) -> PublishResult:
    """Record ``event`` on the ledger (when the catalog says so), then fan it out."""
    book = ledger if ledger is not None else load_ledger(cli_config)
    should_record = is_recorded(event.event_type) if record is None else bool(record)
    recorded: Optional[PostResult] = None
    if should_record and event.source != book.name:
        try:
            recorded = book.record(event)
        except Exception as exc:  # noqa: BLE001 — a ledger bug never breaks the caller
            logger.exception("ledger %s record raised", book.name)
            recorded = PostResult(channel=book.name, ok=False, error=str(exc))
        if recorded.ok:
            eventlog.emit(
                "bus.recorded",
                ledger=book.name,
                work_item=recorded.ref or event.work_item,
                event_type=event.event_type,
                source=event.source,
                url=recorded.url or None,
            )
            if recorded.url and not event.url:
                event = replace(event, url=recorded.url)
            if recorded.ref and not event.work_item:
                event = replace(event, work_item=recorded.ref)
        else:
            eventlog.emit(
                "bus.record_failed",
                level="warning",
                ledger=book.name,
                work_item=event.work_item or None,
                event_type=event.event_type,
                source=event.source,
                error=recorded.error or None,
            )

    resolved = (
        list(channels)
        if channels is not None
        else load_channels(cli_config, client_factory=client_factory)
    )
    posts: List[PostResult] = []
    for channel in resolved:
        if channel.name == event.source or not channel.subscribes(event.event_type):
            continue
        try:
            result = channel.post(event)
        except ChannelError as exc:
            result = PostResult(channel=channel.name, ok=False, error=str(exc))
        except Exception as exc:  # a provider bug never breaks the caller
            logger.exception("channel %s post raised", channel.name)
            result = PostResult(channel=channel.name, ok=False, error=str(exc))
        if result.ok:
            eventlog.emit(
                "channel.posted",
                channel=result.channel,
                work_item=event.work_item,
                event_type=event.event_type,
                thread=result.thread or None,
            )
        else:
            eventlog.emit(
                "channel.post_failed",
                level="warning",
                channel=result.channel,
                work_item=event.work_item,
                event_type=event.event_type,
                error=result.error or None,
            )
        posts.append(result)
    eventlog.emit(
        "bus.published",
        level="debug",
        work_item=event.work_item or None,
        event_type=event.event_type,
        source=event.source,
        recorded=bool(recorded and recorded.ok) if should_record else None,
        posted=sum(1 for post in posts if post.ok),
        channels=[post.channel for post in posts],
    )
    # Nobody took it (issue-409): queue it rather than lose it. Three guards, each
    # load-bearing. `cli_config` — without one there is no state root to write
    # under, and a bare `publish(event, channels=[...])` must not create
    # `./.the-loop`. `channels is None` — the bus resolved the channels itself; an
    # injected list is a caller's one-off (a test, an embedder) whose failures are
    # that caller's to interpret. `posts` — at least one channel was ASKED: an
    # event nobody subscribes to was never going to be delivered, and queueing it
    # would make the outbox a log of everything.
    if cli_config and channels is None and posts and not any(post.ok for post in posts):
        from . import outbox

        try:
            outbox.remember(event, posts, cli_config)
        except Exception:  # noqa: BLE001 — a failed queue never changes the result
            logger.exception("could not queue the undelivered %s", event.event_type)
    return PublishResult(record=recorded, posts=posts)


def open_conversation(
    work_item: str,
    cli_config: Optional[Mapping[str, Any]] = None,
    *,
    channels: Optional[Sequence[Channel]] = None,
    client_factory: Optional[Callable] = None,
) -> List[PostResult]:
    """Open ``work_item``'s conversation on every enabled channel that can
    (issue-317 R1.1, R1.6).

    A channel *can* when it is :class:`Conversational` — the Slack bot is; the
    GitHub ledger is not, because the work item is its conversation — and the
    call is idempotent by the channel's contract: a bound work item gets its
    existing thread back and nothing is posted. Best-effort per channel (R1.5):
    a ``ChannelError`` or any other exception is a failed ``PostResult`` plus
    ``channel.open_failed`` (ids only), and the remaining channels are still
    asked. A fresh open is announced by the channel itself
    (``channel.thread_opened``); an idempotent one is silent. An empty
    ``work_item`` opens nothing.
    """
    if not work_item:
        return []
    resolved = (
        list(channels)
        if channels is not None
        else load_channels(cli_config, client_factory=client_factory)
    )
    results: List[PostResult] = []
    for channel in resolved:
        if not isinstance(channel, Conversational):
            continue
        try:
            result = channel.open(work_item)
        except ChannelError as exc:
            result = PostResult(channel=channel.name, ok=False, error=str(exc))
        except Exception as exc:  # a provider bug never breaks the caller
            logger.exception("channel %s open raised", channel.name)
            result = PostResult(channel=channel.name, ok=False, error=str(exc))
        if not result.ok:
            eventlog.emit(
                "channel.open_failed",
                level="warning",
                channel=result.channel,
                work_item=work_item,
                error=result.error or None,
            )
        results.append(result)
    return results


def broadcast(
    event_type: str,
    work_item: str,
    text: str,
    url: str = "",
    detail: Optional[Mapping[str, str]] = None,
    cli_config: Optional[Mapping[str, Any]] = None,
    channels: Optional[Sequence[Channel]] = None,
    client_factory: Optional[Callable] = None,
) -> List[PostResult]:
    """Fan ``text`` out to every subscribed channel — never recording (issue-245's
    contract, kept for callers that already wrote the work item themselves)."""
    return publish(
        Event(
            event_type=event_type,
            work_item=work_item,
            text=text,
            url=url,
            detail=dict(detail or {}),
        ),
        cli_config,
        channels=channels,
        client_factory=client_factory,
        record=False,
    ).posts
