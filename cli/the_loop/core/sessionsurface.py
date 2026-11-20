"""Core capability: a session's derived state, as the status surfaces show it
(issue-551, R7).

`the-loop check`, `the-loop sessions list` and the attention list all read
:mod:`sessionstate` through here: one read of the event log per call, and one
wording of the state. No rule lives in this module — what "idle" or "an open
ask" means is :func:`sessionstate.derive`'s alone.

Read-only: it reads the machine's event log, writes nothing and emits nothing.

Spec: docs/specs/issue-551/design/messages.html § 6.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .. import cli_config, eventlog, strings
from ..state import layout_from_config
from ..watchconfig import AsksConfig, WatchdogConfig
from . import sessionstate
from .sessionstate import SessionState

__all__ = ["Reader", "clock", "elapsed", "log_path", "nudges", "summary"]


def log_path(config: Optional[dict]) -> str:
    """The event log the service writes to: the same file the stop check reads."""
    data = config or {}
    explicit = (data.get("eventLog") or {}).get("path")
    if explicit:
        return str(explicit)
    if config:
        return str(layout_from_config(data).event_log)
    return str(eventlog.load_config().get("path", eventlog.DEFAULT_PATH))


class Reader:
    """The event log, read once: call it with a work item's ref for its state.

    ``refs`` lists the work items the log has records for, in the order the
    log first names them.
    """

    def __init__(
        self, config: Optional[dict] = None, now: Optional[datetime] = None
    ) -> None:
        data = config or {}
        routing = (
            (data.get("routing") or {}) if config else cli_config.load_routing_config()
        )
        self._watchdog = WatchdogConfig.from_mapping(routing.get("watchdog") or {})
        self._asks = AsksConfig.from_mapping(routing.get("asks") or {})
        self._grouped = sessionstate.load(log_path(config))
        #: Aware, in the zone the times of day are shown in.
        self.now = now or datetime.now().astimezone()
        self.refs: List[str] = list(self._grouped)

    def __call__(self, ref: str) -> SessionState:
        return sessionstate.derive(
            self._grouped.get(ref, []),
            now=self.now,
            watchdog=self._watchdog,
            asks=self._asks,
            work_item=ref,
        )

    def view(self, ref: str) -> Dict[str, Any]:
        """The contract's `session` object, with the state as one line."""
        state = self(ref)
        return {
            **sessionstate.session_view(state),
            "summary": summary(state, self.now),
        }


def clock(stamp: Optional[str], now: datetime) -> str:
    """``stamp`` as a time of day in ``now``'s zone, with the date when it is
    another day's. An unreadable stamp is shown as it is."""
    moment = sessionstate.parse_ts(stamp)
    if moment is None:
        return stamp or "?"
    local = moment.astimezone(now.tzinfo or timezone.utc)
    same_day = local.date() == now.date()
    return local.strftime("%H:%M" if same_day else "%Y-%m-%d %H:%M")


def elapsed(stamp: Optional[str], now: datetime) -> str:
    """How long ago ``stamp`` was: `4 min`, `3 h 5 min`."""
    moment = sessionstate.parse_ts(stamp)
    minutes = 0 if moment is None else max(0, int((now - moment).total_seconds()) // 60)
    if minutes < 120:
        return strings.t("core.sessionsurface.minutes", minutes=minutes)
    return strings.t(
        "core.sessionsurface.hours", hours=minutes // 60, minutes=minutes % 60
    )


def nudges(state: SessionState) -> str:
    """`2 nudges`, and that a person was told once the notice went out."""
    if state.nudges_spent == 1:
        text = strings.t("core.sessionsurface.nudge")
    else:
        text = strings.t("core.sessionsurface.nudges", count=state.nudges_spent)
    if state.notified:
        return strings.t("core.sessionsurface.notified", nudges=text)
    return text


def summary(state: SessionState, now: datetime) -> str:
    """The state as the one line `the-loop check` prints after `session:`."""
    at = strings.t("core.sessionsurface.at", node=state.node) if state.node else ""
    since = clock(state.since, now)
    if state.state == "not-watched":
        return strings.t("core.sessionsurface.not-watched")
    if state.state == "working":
        return strings.t("core.sessionsurface.working", since=since)
    if state.state == "idle":
        return strings.t(
            "core.sessionsurface.idle",
            at=at,
            since=since,
            elapsed=elapsed(state.since, now),
        )
    if state.state == "stalled":
        return strings.t(
            "core.sessionsurface.stalled",
            at=at,
            since=since,
            elapsed=elapsed(state.since, now),
            nudges=nudges(state),
        )
    ask, wait = state.open_ask, state.declared_wait
    if state.reason == "open-ask" and ask is not None:
        asked = clock(ask.asked_at, now)
        if ask.default_at is None:
            return strings.t("core.sessionsurface.asked", asked=asked)
        return strings.t(
            "core.sessionsurface.asked-with-default",
            asked=asked,
            default=ask.default,
            default_at=clock(ask.default_at, now),
        )
    if state.reason == "declared-wait" and wait is not None:
        return strings.t(
            "core.sessionsurface.declared-wait",
            condition=wait.condition,
            until=clock(wait.until, now),
        )
    return strings.t(
        "core.sessionsurface.waiting",
        detail=sessionstate.session_view(state)["detail"],
    )
