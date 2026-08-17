"""The daemons' hook: poll-mode reads on a background thread (R4.1).

The self-diagnosis watcher's shape exactly (issue-242): a daemon thread
looping ``stop_event.wait(interval)`` → one cycle; the caller's existing stop
event ends it; a failing cycle is logged and the thread lives on — channel
machinery never kills ingress.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Mapping, Optional

logger = logging.getLogger("the-loop.channels")

__all__ = ["start_watcher"]


def start_watcher(
    cli_config: Optional[Mapping[str, Any]],
    stop_event: threading.Event,
    *,
    interval_override: Optional[float] = None,
) -> Optional[threading.Thread]:
    """A background reply-reader, or ``None`` when there is nothing to read.

    ``None`` unless the Slack channel is enabled with ``read.mode: poll`` —
    ``socket`` deployments run ``the-loop channels listen`` instead (a
    WebSocket's reconnect lifecycle does not belong inside a poll loop, D5),
    and ``off`` means exactly that.
    """
    from .slack import SlackChannelConfig

    config = SlackChannelConfig.from_mapping(cli_config)
    if not config.enabled or config.read_mode != "poll":
        return None
    interval = (
        interval_override
        if interval_override is not None
        else config.read_interval_seconds
    )
    frozen_config = dict(cli_config or {})

    def run() -> None:
        while not stop_event.wait(interval):
            try:
                from . import inbound

                inbound.poll_once(frozen_config)
            except Exception:  # noqa: BLE001 — never kill ingress over a channel
                logger.exception("channels poll cycle raised; continuing")

    thread = threading.Thread(target=run, name="the-loop-channels", daemon=True)
    thread.start()
    logger.info(
        "channels: reading slack replies every %ss (bound threads only)", interval
    )
    return thread
