"""Core capability: the silent-session watchdog (issue-340, part 2).

Progress reports (:mod:`the_loop.core.progress`) tell a person a session is alive. The
watchdog tells them when it has *stopped* being: a session that has produced no event of
any kind for ``progress.silenceSeconds`` gets one ``session.silent`` event, so "hard work,
stuck loop, dead session" stop looking identical from a phone.

It reads what is already recorded and adds nothing to the daemons' work:

* **Which sessions.** The registry's ``active`` sessions, never a paused or closed one.
* **What counts as activity.** The newest event-log record naming the work item, except
  the watchdog's own and the ``bus.*`` / ``channel.*`` bookkeeping that follows every
  publish — otherwise reporting the silence would end it.
* **Which work items.** The same opt-in as progress reports: only an item carrying
  ``progress.label``. The label is read only for a session already past the threshold,
  so a healthy deployment makes no tracker call at all.
* **Once, not forever.** One event per silence; the next needs activity in between.

It runs inside a daemon that already exists, as self-diagnosis does
(:func:`start_watcher`), and is off unless ``progress.silenceSeconds`` is above zero. It
cannot report on a daemon that is itself dead — a stuck session, not a stuck poller.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Union
from pathlib import Path

from .. import eventlog
from . import progress as core_progress

logger = logging.getLogger("the-loop.silence")

__all__ = ["scan", "start_watcher", "watch_interval"]

#: Records that are the watchdog's own wake, or the bookkeeping every publish leaves —
#: none is the session doing anything.
_NOT_ACTIVITY = ("session.silent", "bus.*", "channel.*")


def watch_interval(silence_seconds: int) -> int:
    """How often to look: a quarter of the threshold, never faster than every 30s or
    slower than every 5 minutes, so a report is at most a quarter-threshold late."""
    return max(30, min(300, silence_seconds // 4))


def _parse(ts: Any) -> Optional[datetime]:
    text = str(ts or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _is_noise(event: str) -> bool:
    import fnmatch

    return any(fnmatch.fnmatch(event, pattern) for pattern in _NOT_ACTIVITY)


def _humanize(seconds: int) -> str:
    minutes = max(1, seconds // 60)
    if minutes < 90:
        return f"{minutes} minutes"
    return f"{minutes / 60:.1f} hours"


def scan(
    config: Optional[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
    log_path: Optional[Union[str, Path]] = None,
) -> List[str]:
    """One pass: emit ``session.silent`` for each silent, opted-in session; return
    the refs it spoke for. A fault in one session never stops the rest."""
    from ..channels.base import Event
    from ..channels.bus import publish as bus_publish
    from ..state import layout_from_config
    from ..workitem import WorkItemRef
    from . import sessions as core_sessions

    settings = core_progress.ProgressConfig.from_config(config)
    if not (settings.enabled and settings.silence_seconds > 0):
        return []
    document = dict(config or {})
    path = str(log_path or layout_from_config(document).event_log)
    now = now or datetime.now(timezone.utc)

    sessions = core_sessions.list_sessions(status="active", config=document)
    wanted = {str(s.get("ref") or ""): s for s in sessions if s.get("ref")}
    if not wanted:
        return []

    activity: Dict[str, datetime] = {}
    silenced: Dict[str, datetime] = {}
    for record in eventlog.read_events(path):
        stamp = _parse(record.get("ts"))
        if stamp is None:
            continue
        name = str(record.get("event") or "")
        for ref in {str(record.get("work_item") or ""), *record.get("work_items", [])}:
            if ref not in wanted:
                continue
            if name == "session.silent":
                silenced[ref] = max(stamp, silenced.get(ref, stamp))
            elif not _is_noise(name):
                activity[ref] = max(stamp, activity.get(ref, stamp))

    spoken: List[str] = []
    for ref, session in wanted.items():
        try:
            since = activity.get(ref) or _parse(session.get("createdAt"))
            if since is None:
                continue
            quiet = int((now - since).total_seconds())
            if quiet < settings.silence_seconds:
                continue
            if ref in silenced and silenced[ref] >= since:
                continue  # already said so for this silence
            item = WorkItemRef.parse(ref)
            if not core_progress._label_matches(
                settings.label, core_progress._labels_of(item, document), item.provider
            ):
                continue
            text = (
                f"Nothing has happened on this work item for {_humanize(quiet)} — "
                "the session may be stuck."
            )
            published = bus_publish(
                Event(
                    event_type="session.silent",
                    work_item=ref,
                    text=text,
                    detail={"silent_seconds": str(quiet)},
                    source="loop",
                ),
                document,
                record=False,
            )
            eventlog.emit(
                "session.silent",
                level="warning",
                work_item=ref,
                silent_seconds=quiet,
                channels_posted=sum(1 for posted in published.posts if posted.ok),
            )
            spoken.append(ref)
        except Exception:  # noqa: BLE001 — one item's fault never stops the rest
            logger.exception("silence watchdog: could not check %s", ref)
    return spoken


def start_watcher(
    cli_config: Optional[Mapping[str, Any]],
    stop_event: threading.Event,
    *,
    log_path: Optional[Union[str, Path]] = None,
) -> Optional[threading.Thread]:
    """The daemons' hook: a background watchdog, or ``None`` when the operator never
    asked for one (``progress.silenceSeconds`` unset or ``0``) or it cannot work (the
    event log is the clock, so it must be on).

    A daemon thread looping ``stop_event.wait(interval)`` → :func:`scan`; the caller's
    stop event ends it, and a failing scan is logged and the thread lives on.
    """
    settings = core_progress.ProgressConfig.from_config(cli_config)
    if not (settings.enabled and settings.silence_seconds > 0):
        return None
    if not bool(((cli_config or {}).get("eventLog") or {}).get("enabled", True)):
        logger.warning(
            "progress.silenceSeconds is set but eventLog.enabled is false; the "
            "silence watchdog reads the event log and is not started"
        )
        return None
    interval = watch_interval(settings.silence_seconds)

    def run() -> None:
        while not stop_event.wait(interval):
            try:
                scan(cli_config, log_path=log_path)
            except Exception:  # noqa: BLE001 — never kill ingress over o11y
                logger.exception("silence watchdog scan raised; continuing")

    thread = threading.Thread(target=run, name="the-loop-silence", daemon=True)
    thread.start()
    logger.info(
        "silence watchdog checking every %ss for sessions quiet over %ss",
        interval,
        settings.silence_seconds,
    )
    return thread
