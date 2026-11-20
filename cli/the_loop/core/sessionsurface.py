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

import dataclasses
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .. import cli_config, eventlog, strings
from ..state import layout_from_config
from ..watchconfig import AsksConfig, WatchdogConfig
from . import sessionstate
from .sessionstate import OpenAsk, SessionState

__all__ = [
    "Reader",
    "clock",
    "default_clause",
    "elapsed",
    "log_path",
    "nudges",
    "one_line",
    "shown_ask",
    "summary",
]


#: How much of a question or a default one line of a terminal shows.
MAX_SHOWN = 80
#: A declared wait's condition is at most this long when the command wrote it.
MAX_CONDITION_SHOWN = 200


def one_line(text: Optional[str], limit: int = MAX_SHOWN) -> str:
    """``text`` as one line of printable words, cut to ``limit`` characters.

    A question and a default are a session's own words, and a status line is
    drawn by a terminal: a line break in them would start a line that looks like
    the-loop's, and an escape sequence would be obeyed. Every run of whitespace
    and of characters that do not print becomes one space.
    """
    flat = " ".join("".join(c if c.isprintable() else " " for c in text or "").split())
    return flat if len(flat) <= limit else flat[:limit].rstrip() + "…"


def _shown(state: SessionState) -> SessionState:
    """``state`` with the session's own words made safe to print."""

    def ask_shown(ask: OpenAsk) -> OpenAsk:
        default = None if ask.default is None else one_line(ask.default)
        return dataclasses.replace(
            ask, question=one_line(ask.question), default=default
        )

    wait = state.declared_wait
    return dataclasses.replace(
        state,
        open_asks=tuple(ask_shown(ask) for ask in state.open_asks),
        open_ask=None if state.open_ask is None else ask_shown(state.open_ask),
        declared_wait=(
            None
            if wait is None
            else dataclasses.replace(
                wait, condition=one_line(wait.condition, MAX_CONDITION_SHOWN)
            )
        ),
    )


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
        state = _shown(self(ref))
        view = sessionstate.session_view(state)
        clause = default_clause(state, self.now)
        if clause and view["state"] != "asked":
            # An asked session's detail is its question and default already.
            view["detail"] = "; ".join(
                part for part in (view["detail"], clause) if part
            )
        return {**view, "summary": summary(state, self.now)}


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


def _timed(ask: OpenAsk) -> bool:
    """Whether ``ask``'s default will be taken at a time. An ask recorded
    without an id of its own has no default the watcher takes."""
    return ask.default_at is not None and not ask.legacy


def shown_ask(state: SessionState) -> Tuple[Optional[OpenAsk], int]:
    """The one open ask a line has room for, and how many others are open.

    The ask whose default is due first, because that is the next thing to
    happen by itself; the most recent ask when none has a default.
    """
    asks = state.open_asks
    if not asks:
        return None, 0
    timed = [ask for ask in asks if _timed(ask)]
    if not timed:
        return asks[-1], len(asks) - 1
    far = datetime.max.replace(tzinfo=timezone.utc)
    first = min(timed, key=lambda ask: sessionstate.parse_ts(ask.default_at) or far)
    return first, len(asks) - 1


def _and_more(text: str, more: int) -> str:
    if not more:
        return text
    return strings.t("core.sessionsurface.more", text=text, count=more)


def default_clause(state: SessionState, now: datetime) -> str:
    """`asked 12:01, default “Move it.” at 12:31`; ``""`` when no open ask has
    a default that will be taken.

    Said in every state: a session that asked with a default carries on
    working, and the default is taken whatever it is doing by then.
    """
    ask, more = shown_ask(_shown(state))
    if ask is None or not _timed(ask):
        return ""
    return _and_more(
        strings.t(
            "core.sessionsurface.default-clause",
            asked=clock(ask.asked_at, now),
            default=ask.default,
            default_at=clock(ask.default_at, now),
        ),
        more,
    )


def summary(state: SessionState, now: datetime) -> str:
    """The state as the one line `the-loop check` prints after `session:`."""
    state = _shown(state)
    ask, more = shown_ask(state)
    if state.state == "waiting" and state.reason == "open-ask" and ask is not None:
        asked = clock(ask.asked_at, now)
        if not _timed(ask):
            return _and_more(strings.t("core.sessionsurface.asked", asked=asked), more)
        return _and_more(
            strings.t(
                "core.sessionsurface.asked-with-default",
                asked=asked,
                default=ask.default,
                default_at=clock(ask.default_at, now),
            ),
            more,
        )
    line, clause = _state_line(state, now), default_clause(state, now)
    if not clause:
        return line
    return strings.t("core.sessionsurface.with-default", line=line, clause=clause)


def _state_line(state: SessionState, now: datetime) -> str:
    """The state's own line, before anything about an open ask."""
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
    wait = state.declared_wait
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
