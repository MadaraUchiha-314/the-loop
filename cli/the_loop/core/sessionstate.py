"""Core capability: the state of a session, derived from the event log.

One read-only function of a work item's event records and a clock value:
working, waiting, idle, stalled or not watched, plus what the watcher owes right
now. The stop check, the watcher and the status surfaces all read it, which is
what keeps "idle" on a status line and "idle" in the watcher from disagreeing.

:func:`derive` reads no file and no clock, writes nothing and emits nothing. An
act is owed only while the log holds no record of it, so deriving again after
the watcher recorded an act — or after a restart — never owes it twice.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from .. import strings
from ..watchconfig import AsksConfig, WatchdogConfig

__all__ = [
    "DeclaredWait",
    "Due",
    "EVENTS",
    "OpenAsk",
    "SessionState",
    "UntoldDefault",
    "derive",
    "load",
    "parse_ts",
    "session_view",
]

_TURN_STARTED = "session.turn_started"
_TURN_ENDED = "session.turn_ended"

#: A turn that ended for one of these waits on something with no time limit.
_UNLIMITED_WAITS = frozenset({"human-gate", "complete", "graph-wait"})

#: A person spoke to the session. Each is written only after the
#: authorized-actor guard passed, and closes every open ask whichever one it
#: names: after a person's word no default may be taken.
_ANSWERS = frozenset({"session.reply_sent", "session.ask_answered"})

#: The watcher took an ask's default. It closes the ask it names and no other.
_DEFAULT_TAKEN = "session.ask_default_taken"

_ASK_CLOSERS = _ANSWERS | {_DEFAULT_TAKEN}

#: Records that start a new nudge budget: the pointer moved, or a person's event
#: reached the session. `dispatch.succeeded` is not here: it also records a CI
#: event, an assignment and the watcher's own paste, and counting those would
#: let a stuck session be nudged without end. It resets the
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

#: Records that move the pointer, and the field that names where it went.
_POINTER_MOVES = {"graph.started": "node", "graph.advanced": "to", "graph.forced": "to"}

#: A node is parked when its exit reports a wait, and a human-owned node is
#: also parked as it is entered (`via: entry`). The log names no node's owner,
#: so the entry park is how a move onto a person's node is recognised.
_PARKED = "graph.parked"

#: A turn that ended for one of these waited on the node it was on, so the wait
#: is over once the pointer has left that node.
_ENDED_BY_A_MOVE = frozenset({"human-gate", "graph-wait"})

#: The dispatcher's delivery record. It carries `actor` only for an authorized
#: person's comment or review.
_DELIVERED = "dispatch.succeeded"

#: Every event type the derivation reads. :func:`load` keeps nothing else.
EVENTS = frozenset(
    {
        _DELIVERED,
        _PARKED,
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
    #: The record carries no `ask_id`: it was written when nothing recorded an
    #: answer given on the ticket, so it may have been answered long ago. Such
    #: an ask is listed, and nothing is done for it: no reminder, no default,
    #: and it does not excuse a stop.
    legacy: bool = False


@dataclass(frozen=True)
class UntoldDefault:
    """An ask's default that was taken while the session could not be told."""

    ask_id: str
    default: str


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
    #: `pointer-moved` when the pointer left that turn's node afterwards and no
    #: turn has started since: the turn's own reason was about a node the work
    #: item is no longer on.
    reason: str = ""
    #: The node the pointer last moved to since the last turn record, else that
    #: record's node; ``""`` when neither names one.
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
    #: An ask's default was already taken in this visit to the node (the nudge
    #: budget's window). A second timed ask in the same visit would let a
    #: session keep itself waiting on defaults without end.
    default_spent: bool = False
    #: Every ask nothing has closed, oldest first.
    open_asks: Tuple[OpenAsk, ...] = ()
    #: The most recent of them.
    open_ask: Optional[OpenAsk] = None
    declared_wait: Optional[DeclaredWait] = None
    #: The last default taken, when the session was never told of it and no
    #: person has spoken since. The next nudge tells it.
    untold_default: Optional[UntoldDefault] = None
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
    """One open ask while the log is walked."""

    def __init__(self, record: Dict[str, Any], asked: _Moment) -> None:
        self.record = record
        self.asked = asked
        explicit = _text(record, "ask_id")
        self.explicit = bool(explicit)
        self.ask_id = explicit or asked[1]
        self.reminded = False

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
            legacy=not self.explicit,
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
    # The pointer's move since the last turn record, and the last node parked
    # with whether that was the entry park of a person's node.
    pointer: Optional[Tuple[_Moment, str]] = None
    parked = ""
    parked_by_entry = False
    # The open asks by id, oldest first, and when an ask was last closed.
    asks_open: Dict[str, _Ask] = {}
    ask_closed: Optional[_Moment] = None
    nudges_spent = 0
    notified = False
    default_spent = False
    last_nudge: Optional[datetime] = None
    # The stall and number of the last nudge counted.
    last_attempt: Optional[Tuple[str, Any]] = None
    stalls: Dict[str, _Stall] = {}
    unresumed: List[_Stall] = []
    # The last default taken that the session was not told, and the one the
    # last nudge carried: a nudge that did not land leaves it untold.
    untold: Optional[UntoldDefault] = None
    carried: Optional[UntoldDefault] = None

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
            turn, wait, pointer = (event, moment, record), None, None
            for stall in unresumed:
                stall.resumed = when
            unresumed = []
        elif event == _TURN_ENDED:
            turn, wait_at_end, wait = (event, moment, record), wait, None
            pointer = None
        elif event in _POINTER_MOVES:
            target = _text(record, _POINTER_MOVES[event])
            if target:
                pointer = (moment, target)
                # A park is about one visit to its node. The entry park of a
                # person's node is written just before the move onto it.
                if target != parked:
                    parked, parked_by_entry = "", False
        elif event == _PARKED:
            again = parked_by_entry and parked == _text(record, "node")
            parked = _text(record, "node")
            parked_by_entry = again or record.get("via") == "entry"
        elif event == "session.wait_declared":
            wait = (moment, record)
        elif event == "session.awaiting_input":
            asked = _Ask(record, moment)
            asks_open.pop(asked.ask_id, None)
            asks_open[asked.ask_id] = asked
        elif event == "session.ask_reminded":
            reminded = asks_open.get(_text(record, "ask_id"))
            if reminded is not None:
                reminded.reminded = True
        elif event in ("session.nudged", "session.stalled"):
            if event == "session.nudged":
                attempt = (_text(record, "stall_id"), record.get("nudge"))
                # A nudge is recorded before it is pasted. When the paste
                # fails, the same attempt is recorded again with
                # `delivered: false`: one nudge, not two.
                outcome = record.get("delivered") is False and attempt == last_attempt
                if not outcome:
                    nudges_spent, last_nudge = nudges_spent + 1, when
                    last_attempt = attempt
                    told = untold is not None and untold.ask_id == _text(
                        record, "default_of"
                    )
                    carried, untold = (untold, None) if told else (None, untold)
                elif carried is not None:
                    untold, carried = carried, None
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

        if event in _ANSWERS:
            untold = carried = None
            if asks_open:
                asks_open, ask_closed = {}, moment
        elif event == _DEFAULT_TAKEN:
            default_spent = True
            if asks_open.pop(_text(record, "ask_id"), None) is not None:
                ask_closed = moment
            # A record without `delivered: false` is written before the paste;
            # the paste that fails writes the same default again with it.
            untold = carried = None
            if record.get("delivered") is False and _text(record, "default"):
                untold = UntoldDefault(
                    _text(record, "ask_id"), _text(record, "default")
                )
        if event in _BUDGET_RESETS or _delivered_a_person(record, work_item):
            nudges_spent, notified, last_nudge = 0, False, None
            last_attempt, default_spent = None, False

    open_asks = tuple(ask.view() for ask in asks_open.values())
    open_ask = open_asks[-1] if open_asks else None

    due: List[Due] = []
    # A stall is ended whatever the switch says now: it may have been made
    # before the watchdog was turned off.
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
                # An ask without an id excuses no stop, so it holds no wait.
                counted = tuple(ask for ask in open_asks if not ask.legacy)
                if counted:
                    # The wait ends when the last ask closes. That has a time
                    # only when every such ask has a default.
                    ends = [parse_ts(ask.default_at) for ask in counted]
                    known = [end for end in ends if end is not None]
                    if len(known) == len(ends):
                        until = _stamp_of(counted, max(known))
                    state = "waiting"
                else:
                    idle = _later(at, ask_closed)
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
                    # Idle starts when the reason lapsed, not at the turn's end.
                    # An unknown reason is idle from the turn's end.
                    idle = _later(at, lapse)
            if state == "waiting":
                since = at[1]

        # The pointer moved after the turn record and no turn has started
        # since: the paste that should have started one evidently did not.
        if pointer is not None and not _position_unknown(reason, node):
            moved_at, node = pointer
            if kind == _TURN_ENDED and (idle is not None or reason in _ENDED_BY_A_MOVE):
                if parked == node:
                    # The session waits there, as it would had its turn ended
                    # on it: for a person at a node parked on entry, else for
                    # whatever the node's exit reported.
                    reason = "human-gate" if parked_by_entry else "graph-wait"
                    state, since = "waiting", moved_at[1]
                    until = idle = None
                else:
                    reason, idle = "pointer-moved", _later(moved_at, idle)

    stall_id_now: Optional[str] = None
    if idle is not None:
        state, since = "idle", idle[1]
        threshold = timedelta(seconds=watchdog.idle_seconds)
        # The stop check could not tell where the work item stands, which is
        # how every turn of a pull request's own session ends. Nothing says
        # work is owed, so the session never becomes a stall.
        if _position_unknown(reason, node):
            pass
        elif now - idle[0] >= threshold:
            state = "stalled"
            stall_id_now = f"{work_item}@{idle[1]}"
            last_act = max(idle[0], last_nudge) if last_nudge else idle[0]
            if watchdog.enabled and now - last_act >= threshold:
                # The nudge names the node, so a stall without one goes to the
                # notice.
                if node and nudges_spent < watchdog.max_nudges:
                    due.append(Due("nudge", stall_id=stall_id_now))
                elif not notified:
                    due.append(Due("notify", stall_id=stall_id_now))

    for ask in open_asks:
        if ask.legacy:
            continue
        deadline = parse_ts(ask.default_at)
        asked_at = parse_ts(ask.asked_at)
        if deadline is not None:
            if now >= deadline:
                due.append(Due("take-default", ask_id=ask.ask_id))
        elif (
            asks.reminder_seconds > 0
            and not ask.reminded
            and asked_at is not None
            and now - asked_at >= timedelta(seconds=asks.reminder_seconds)
        ):
            due.append(Due("remind", ask_id=ask.ask_id))

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
        default_spent=default_spent,
        open_asks=open_asks,
        open_ask=open_ask,
        declared_wait=declared,
        untold_default=untold,
        due=tuple(due),
    )


def _stamp_of(asks: Tuple[OpenAsk, ...], moment: datetime) -> Optional[str]:
    """The stored text of the default time that parses to ``moment``."""
    for ask in asks:
        if parse_ts(ask.default_at) == moment:
            return ask.default_at
    return None


def _position_unknown(reason: str, node: str) -> bool:
    return reason == "inconclusive" and not node


def _delivered_to(record: Dict[str, Any]) -> str:
    """The session a delivery went to. A delivery to a pull request's own
    session is logged under its work item, with the pull request as
    `endpoint`."""
    return _text(record, "endpoint") or _text(record, "work_item")


def _delivered_a_person(record: Dict[str, Any], to: str = "") -> bool:
    """Whether ``record`` is a person's event delivered to a session; with
    ``to``, to that work item's session and no other."""
    if record.get("event") != _DELIVERED or not _text(record, "actor"):
        return False
    return not to or _delivered_to(record) == to


def _later(first: _Moment, second: Optional[_Moment]) -> _Moment:
    return second if second is not None and second[0] > first[0] else first


def _lapse(wait: Tuple[_Moment, Dict[str, Any]], limit: timedelta) -> Optional[_Moment]:
    """When a declared wait ends; ``None`` when its end cannot be read.

    `the-loop wait` refuses a wait over the limit. The limit is applied again
    here so that a record stating a longer one is not believed.
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


#: A line that can hold a record the derivation reads: one of its event types,
#: quoted as the log writes a value. Most of a busy log fails this test, and a
#: line that fails it is never parsed.
_READ_LINE = re.compile(
    r'"(?:session\.|graph\.(?:started|advanced|forced|parked)"|dispatch\.succeeded")'
)


def load(
    path: Union[str, Path], work_item: Optional[str] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """Read the event log once: the records :func:`derive` reads, by work item.

    The watcher derives every session from one pass, so that costs one read of
    the log however many sessions are live. The file is streamed a line at a
    time and a line is parsed only when its text can hold a record that is
    kept, so the cost follows the session records, not the size of the log.
    ``work_item`` keeps one work item's records and passes over every line
    that does not name it: the watcher's second look before an act. A missing log is no records; a torn or unreadable
    line is skipped.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    # The ref as the log writes it, quotes included.
    named = json.dumps(work_item) if work_item else None
    try:
        handle = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return grouped
    with handle:
        for line in handle:
            if named is not None and named not in line:
                continue
            if _READ_LINE.search(line) is None:
                continue
            # A delivery is kept only when it names a person.
            if '"dispatch.succeeded"' in line and '"actor"' not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            event = record.get("event")
            if not isinstance(event, str) or event not in EVENTS:
                continue
            if event == _DELIVERED and not _delivered_a_person(record):
                continue
            ref = (
                _delivered_to(record)
                if event == _DELIVERED
                else record.get("work_item")
            )
            if not isinstance(ref, str) or not ref:
                continue
            if work_item is None or ref == work_item:
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
        if _position_unknown(state.reason, state.node):
            return strings.t("core.sessionstate.position-unknown")
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
