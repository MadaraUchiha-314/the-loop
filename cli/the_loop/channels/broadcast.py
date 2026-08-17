"""Outbound fan-out: one event, every subscribed channel, best-effort (D3)."""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Mapping, Optional, Sequence

from .. import eventlog
from .base import Channel, ChannelError, OutboundEvent, PostResult, load_channels

logger = logging.getLogger("the-loop.channels")

__all__ = ["broadcast"]


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
    """Post ``text`` to every enabled channel subscribed to ``event_type``.

    Best-effort per channel (R1.2): a failure becomes a ``PostResult`` and a
    ``channel.post_failed`` event, never an exception — the work item already
    carries the text, so a channel outage loses a convenience, not the record.
    """
    resolved = (
        list(channels)
        if channels is not None
        else load_channels(cli_config, client_factory=client_factory)
    )
    event = OutboundEvent(
        event_type=event_type,
        work_item=work_item,
        text=text,
        url=url,
        detail=dict(detail or {}),
    )
    results: List[PostResult] = []
    for channel in resolved:
        if not channel.wants(event_type):
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
                work_item=work_item,
                event_type=event_type,
                thread=result.thread or None,
            )
        else:
            eventlog.emit(
                "channel.post_failed",
                level="warning",
                channel=result.channel,
                work_item=work_item,
                event_type=event_type,
                error=result.error or None,
            )
        results.append(result)
    return results
