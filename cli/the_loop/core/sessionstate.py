"""Core capability: the state of a session, derived from the event log (issue-551).

One read-only function of a work item's event records and a clock value:
working, waiting, idle, stalled or not watched, plus what the watcher owes right
now. The stop check, the watcher and the status surfaces all read it, which is
what keeps "idle" on a status line and "idle" in the watcher from disagreeing
(R7).

:func:`derive` reads no file and no clock, writes nothing and emits nothing. An
act is owed only while the log holds no record of it, so deriving again after
the watcher recorded an act — or after a restart — never owes it twice (R4.10).

Spec: docs/specs/issue-551/design.md § "The state of a session".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from .. import eventlog, strings
from ..watchconfig import AsksConfig, WatchdogConfig

__all__ = [
    "DeclaredWait",
    "Due",
    "EVENTS",
    "OpenAsk",
    "SessionState",
    "derive",
    "load",
    "parse_ts",
    "session_view",
]

_TURN_STARTED = "session.turn_started"
_TURN_ENDED = "session.turn_ended"

#: A turn that ended for one of these waits on something with no time limit.
_UNLIMITED_WAITS = frozenset({"human-gate", "complete", "graph-wait"})

#: Records that close an ask. Each is written only after the authorized-actor
#: guard passed, or by the watcher itself (design § Security design).
_ASK_CLOSERS = frozenset(
    {"session.reply_sent", "session.ask_answered", "session.ask_default_taken"}
)

#: Records that start a new nudge budget: the pointer moved, or a person's event
#: reached the session. `dispatch.succeeded` is not here: it also records a CI
#: event, an assignment and the watcher's own paste, and counting those would
#: let a stuck session be nudged without end (abuse case 5). It resets the
#: budget only when it names the person (:func:`_delivered_a_person`).
_BUDGET_RESETS = frozenset(
    {
        "graph.started",
        "graph.advanced",
        "graph.forced",
        "session.reply_sent",
        "session.ask_answered",
    }
)

#: The dispatcher's delivery record. It carries `actor` only for an authorized
#: person's comment or review.
_DELIVERED = "dispatch.succeeded"

#: Every event type the derivation reads. :func:`load` keeps nothing else.
EVENTS = frozenset(
    {
        _DELIVERED,
        _TURN_STARTED,
        _TURN_ENDED,
        "session.wait_declared",
        "session.nudged",
        "session.stalled",
        "session.stall_ended",
        "session.awaiting_input",
        "session.ask_reminded",
    }
    | _ASK_CLOSERS
    | _BUDGET_RESETS
)


@dataclass(frozen=True)
class OpenAsk:
    """A question the session asked that nothing has closed."""

    #: The record's `ask_id`; the ask's own timestamp for a record without one.
    ask_id: str
    asked_at: str
    question: str
    default: Optional[str]
    #: When the default is taken. ``None`` unless the record carries BOTH a
    #: default and a readable time: anything less is never taken.
    default_at: Optional[str]
    reminded: bool


@dataclass(frozen=True)
class DeclaredWait:
    """What the session said it waits for (`the-loop wait`)."""

    condition: str
    #: When the wait lapses: its stated end, or the wait limit if that is sooner.
    until: str
    declared_at: str
    #: ``True`` only for a wait made since the last turn record and not yet
    #: lapsed. A wait covers the one stop that ends the turn it was made in.
    covers_stop: bool


@dataclass(frozen=True)
class Due:
    """One act the watcher owes: `nudge`, `notify`, `end-stall`, `take-default`
    or `remind`."""

    act: str
    stall_id: Optional[str] = None
    #: `end-stall` only: how long the stall lasted. ``None`` when its start
    #: cannot be read.
    idle_seconds: Optional[int] = None
    ask_id: Optional[str] = None


@dataclass(frozen=True)
class SessionState:
    work_item: str
    #: `not-watched` | `working` | `waiting` | `idle` | `stalled`.
    state: str
    #: The reason of the turn end behind a waiting, idle or stalled state.
    reason: str = ""
    #: The node of the last turn record; ``""`` when it names none.
    node: str = ""
    #: When the current state began. A stall began when the idle period did.
    since: Optional[str] = None
    #: When a time-limited wait lapses.
    until: Optional[str] = None
    idle_since: Optional[str] = None
    #: Set once the idle threshold has passed.
    stall_id: Optional[str] = None
    #: Nudges already sent in this visit to the node.
    nudges_spent: int = 0
    #: The one stall notice of this visit to the node was already sent.
    notified: bool = False
    open_ask: Optional[OpenAsk] = None
    declared_wait: Optional[DeclaredWait] = None
    #: In the order the watcher performs them.
    due: Tuple[Due, ...] = ()


def parse_ts(value: Any) -> Optional[datetime]:
    """An event-log timestamp as an aware UTC time; ``None`` for anything else."""
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value[-1] in "Zz" else value
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _utc(moment)


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _stamp(moment: datetime) -> str:
    """``moment`` in the event log's own form, for a time no record states."""
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _text(record: Dict[str, Any], key: str) -> str:
    value = record.get(key)
    return value if isinstance(value, str) else ""


#: A moment and the text that names it. The stored text is kept beside the
#: parsed time because a stall id is built from it and must not change with
#: formatting.
_Moment = Tuple[datetime, str]


class _Ask:
    """The latest ask while the log is walked."""

    def __init__(self, record: Dict[str, Any], asked: _Moment) -> None:
        self.record = record
        self.asked = asked
        explicit = _text(record, "ask_id")
        self.explicit = bool(explicit)
        self.ask_id = explicit or asked[1]
        self.closed: Optional[_Moment] = None
        self.reminded = False

    def closed_by(self, record: Dict[str, Any]) -> bool:
        other = _text(record, "ask_id")
        # `reply_sent` names no ask, and neither does an ask written before
        # issue-551: then the order of the records decides.
        return not (self.explicit and other) or other == self.ask_id

    def view(self) -> OpenAsk:
        default = _text(self.record, "default") or None
        default_at = _text(self.record, "default_at")
        timed = default is not None and parse_ts(default_at) is not None
        return OpenAsk(
            ask_id=self.ask_id,
            asked_at=self.asked[1],
            question=_text(self.record, "question").strip(),
            default=default,
            default_at=default_at if timed else None,
            reminded=self.reminded,
        )


class _Stall:
    """A stall the watcher acted on, until a `stall_ended` names it."""

    def __init__(self) -> None:
        self.idle_since: Optional[datetime] = None
        self.resumed: Optional[datetime] = None


def derive(
    events: Iterable[Any],
    *,
    now: datetime,
    watchdog: WatchdogConfig,
    asks: AsksConfig,
    work_item: str,
) -> SessionState:
    """The state of ``work_item``'s session at ``now``.

    ``events`` are that work item's records, oldest first, as the event log
    stores them (:func:`load` groups them). A record that is not a mapping, or
    has no readable ``ts``, is skipped.
    """
    now = _utc(now)
    turn: Optional[Tuple[str, _Moment, Dict[str, Any]]] = None
    # The wait made since the last turn record, and the one behind the last end.
    wait: Optional[Tuple[_Moment, Dict[str, Any]]] = None
    wait_at_end: Optional[Tuple[_Moment, Dict[str, Any]]] = None
    ask: Optional[_Ask] = None
    nudges_spent = 0
    notified = False
    last_nudge: Optional[datetime] = None
    stalls: Dict[str, _Stall] = {}
    unresumed: List[_Stall] = []

    for record in events:
        if not isinstance(record, dict):
            continue
        event = record.get("event")
        if not isinstance(event, str) or event not in EVENTS:
            continue
        when = parse_ts(record.get("ts"))
        if when is None:
            continue
        moment: _Moment = (when, record["ts"])

        if event == _TURN_STARTED:
            turn, wait = (event, moment, record), None
            for stall in unresumed:
                stall.resumed = when
            unresumed = []
        elif event == _TURN_ENDED:
            turn, wait_at_end, wait = (event, moment, record), wait, None
        elif event == "session.wait_declared":
            wait = (moment, record)
        elif event == "session.awaiting_input":
            ask = _Ask(record, moment)
        elif event == "session.ask_reminded":
            if ask is not None and _text(record, "ask_id") == ask.ask_id:
                ask.reminded = True
        elif event in ("session.nudged", "session.stalled"):
            if event == "session.nudged":
                nudges_spent, last_nudge = nudges_spent + 1, when
            else:
                notified = True
            stall_id = _text(record, "stall_id")
            if stall_id:
                stall = stalls.get(stall_id)
                if stall is None:
                    stall = stalls[stall_id] = _Stall()
                    # The id is the work item and the idle period's start.
                    stall.idle_since = parse_ts(record.get("idle_since")) or parse_ts(
                        stall_id.rpartition("@")[2]
                    )
                # Only a turn that starts after the last act ends the stall.
                if stall.resumed is None and stall not in unresumed:
                    unresumed.append(stall)
        elif event == "session.stall_ended":
            ended = stalls.pop(_text(record, "stall_id"), None)
            if ended is not None and ended in unresumed:
                unresumed.remove(ended)

        if event in _ASK_CLOSERS:
            if ask is not None and ask.closed is None and ask.closed_by(record):
                ask.closed = moment
        if event in _BUDGET_RESETS or _delivered_a_person(record):
            nudges_spent, notified, last_nudge = 0, False, None

    open_ask = ask.view() if ask is not None and ask.closed is None else None

    due: List[Due] = []
    # A stall is ended whatever the switch says now: it may have been made
    # before the watchdog was turned off (R4.5).
    for stall_id, stall in stalls.items():
        if stall.resumed is not None:
            lasted = (
                int((stall.resumed - stall.idle_since).total_seconds())
                if stall.idle_since is not None
                else None
            )
            due.append(Due("end-stall", stall_id=stall_id, idle_seconds=lasted))

    state, reason, node = "not-watched", "", ""
    since: Optional[str] = None
    until: Optional[str] = None
    idle: Optional[_Moment] = None
    declared: Optional[DeclaredWait] = None
    limit = timedelta(seconds=watchdog.max_wait_seconds)

    if wait is not None:
        lapse = _lapse(wait, limit)
        if lapse is not None:
            declared = _declared(wait, lapse, covers_stop=now < lapse[0])

    if turn is not None:
        kind, at, record = turn
        node = _text(record, "node")
        if kind == _TURN_STARTED:
            state, since = "working", at[1]
        else:
            reason = _text(record, "reason")
            lapse = None
            if reason in _UNLIMITED_WAITS:
                state = "waiting"
            elif reason == "open-ask":
                if open_ask is not None:
                    state, until = "waiting", open_ask.default_at
                else:
                    idle = _later(at, ask.closed if ask is not None else None)
            elif reason == "declared-wait" and wait_at_end is not None:
                lapse = _lapse(wait_at_end, limit)
            elif reason == "background-work":
                # Background work is believed for the wait limit, then not.
                ends = at[0] + limit
                lapse = (ends, _stamp(ends))
            if state != "waiting" and idle is None:
                if lapse is not None and now < lapse[0]:
                    state, until = "waiting", lapse[1]
                    if reason == "declared-wait" and wait_at_end is not None:
                        declared = declared or _declared(
                            wait_at_end, lapse, covers_stop=False
                        )
                else:
                    # Idle starts when the reason lapsed, not at the turn's end
                    # (R4.8). An unknown reason is idle from the turn's end.
                    idle = _later(at, lapse)
            if state == "waiting":
                since = at[1]

    stall_id_now: Optional[str] = None
    if idle is not None:
        state, since = "idle", idle[1]
        threshold = timedelta(seconds=watchdog.idle_seconds)
        if now - idle[0] >= threshold:
            state = "stalled"
            stall_id_now = f"{work_item}@{idle[1]}"
            last_act = max(idle[0], last_nudge) if last_nudge else idle[0]
            if watchdog.enabled and now - last_act >= threshold:
                # The nudge names the node, so a stall without one goes to the
                # notice (design § Fail-closed).
                if node and nudges_spent < watchdog.max_nudges:
                    due.append(Due("nudge", stall_id=stall_id_now))
                elif not notified:
                    due.append(Due("notify", stall_id=stall_id_now))

    if open_ask is not None:
        deadline = parse_ts(open_ask.default_at)
        asked_at = parse_ts(open_ask.asked_at)
        if deadline is not None:
            if now >= deadline:
                due.append(Due("take-default", ask_id=open_ask.ask_id))
        elif (
            asks.reminder_seconds > 0
            and not open_ask.reminded
            and asked_at is not None
            and now - asked_at >= timedelta(seconds=asks.reminder_seconds)
        ):
            due.append(Due("remind", ask_id=open_ask.ask_id))

    return SessionState(
        work_item=work_item,
        state=state,
        reason=reason,
        node=node,
        since=since,
        until=until,
        idle_since=idle[1] if idle is not None else None,
        stall_id=stall_id_now,
        nudges_spent=nudges_spent,
        notified=notified,
        open_ask=open_ask,
        declared_wait=declared,
        due=tuple(due),
    )


def _delivered_a_person(record: Dict[str, Any]) -> bool:
    return record.get("event") == _DELIVERED and bool(_text(record, "actor"))


def _later(first: _Moment, second: Optional[_Moment]) -> _Moment:
    return second if second is not None and second[0] > first[0] else first


def _lapse(wait: Tuple[_Moment, Dict[str, Any]], limit: timedelta) -> Optional[_Moment]:
    """When a declared wait ends; ``None`` when its end cannot be read.

    `the-loop wait` refuses a wait over the limit. The limit is applied again
    here so that a record stating a longer one is not believed (abuse case 4).
    """
    (declared_at, _), record = wait
    stated = parse_ts(record.get("until"))
    if stated is None:
        return None
    capped = declared_at + limit
    if stated <= capped:
        return (stated, record["until"])
    return (capped, _stamp(capped))


def _declared(
    wait: Tuple[_Moment, Dict[str, Any]], lapse: _Moment, *, covers_stop: bool
) -> DeclaredWait:
    (_, declared_at), record = wait
    return DeclaredWait(
        condition=_text(record, "condition"),
        until=lapse[1],
        declared_at=declared_at,
        covers_stop=covers_stop,
    )


def load(path: Union[str, Path]) -> Dict[str, List[Dict[str, Any]]]:
    """Read the event log once: the records :func:`derive` reads, by work item.

    The watcher derives every session from one pass, so a tick costs one read of
    the log however many sessions are live. A missing log is no records.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for record in eventlog.read_events(path):
        event = record.get("event")
        if event not in EVENTS:
            continue
        if event == _DELIVERED and not _delivered_a_person(record):
            continue  # most of a busy log, and nothing the derivation reads
        ref = record.get("work_item")
        if isinstance(ref, str) and ref:
            grouped.setdefault(ref, []).append(record)
    return grouped


def session_view(state: SessionState) -> Dict[str, Any]:
    """``state`` as the contract's `session` object (the check response).

    `asked` is a session that waits on an open ask.
    """
    asked = state.state == "waiting" and state.reason == "open-ask"
    return {
        "state": "asked" if asked else state.state,
        "node": state.node,
        "since": state.since,
        "detail": _detail(state),
    }


def _detail(state: SessionState) -> str:
    """What a waiting session waits for, the question of an asked one."""
    if state.state == "not-watched":
        return strings.t("core.sessionstate.not-watched")
    if state.state == "stalled":
        if state.notified:
            return strings.t("core.sessionstate.notified", nudges=state.nudges_spent)
        return strings.t("core.sessionstate.stalled", nudges=state.nudges_spent)
    if state.state == "idle":
        return strings.t("core.sessionstate.idle")
    if state.state != "waiting":
        return ""
    ask, wait = state.open_ask, state.declared_wait
    if state.reason == "open-ask" and ask is not None:
        if ask.default_at is None:
            return ask.question or strings.t("core.sessionstate.asked")
        return strings.t(
            "core.sessionstate.asked-with-default",
            question=ask.question,
            default=ask.default,
            default_at=ask.default_at,
        )
    if state.reason == "declared-wait" and wait is not None:
        return strings.t(
            "core.sessionstate.declared-wait",
            condition=wait.condition,
            until=wait.until,
        )
    if state.reason == "background-work":
        return strings.t("core.sessionstate.background-work", until=state.until)
    if state.reason == "human-gate":
        return strings.t("core.sessionstate.human-gate")
    if state.reason == "complete":
        return strings.t("core.sessionstate.complete")
    return strings.t("core.sessionstate.graph-wait")
