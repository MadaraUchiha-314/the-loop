"""Core capability: the watcher (issue-551, Requirement 4, R6.2, R6.7).

One thread in the control-plane service, on a fixed tick. Each cycle reads the
event log once, derives every live session's state (:mod:`sessionstate`) and
performs what that state owes: a nudge, the one stall notice, the end of a
stall, an ask's default, an ask's reminder.

The watcher keeps no state of its own. An act is owed only while the log holds
no record of it, and every act here ends by writing that record, so a second
cycle, or a watcher started after a restart, repeats nothing (R4.10, R6.10).

This is the one place the daemon types into a session with no human event
behind it. What it types is a fixed prompt file plus the node id and its
command from the graph definition, the idle minutes and the work item's own
ref (:func:`nudge_text`); the "proceed with your default" message quotes the
session's own default inside a fence it cannot close (:func:`default_text`).
Nothing a commenter wrote is ever in either.

Spec: docs/specs/issue-551/design.md § "The watcher's cycle".
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Union
from pathlib import Path

from .. import eventlog, prompts
from ..channels import sessionnotes
from ..channels.base import Event
from ..sessions.registry import Session, SessionRegistry
from ..watchconfig import AsksConfig, WatchdogConfig
from . import graphs as core_graphs
from . import sessions as core_sessions
from . import sessionstate, sessionsurface, stopcheck
from .sessionstate import Due, SessionState

logger = logging.getLogger("the-loop.core.watchdog")

__all__ = [
    "TICK_SECONDS",
    "default_text",
    "nudge_text",
    "run_cycle",
    "start_watcher",
]

#: How often the watcher looks. Fixed: the thresholds it acts on are minutes
#: long, and they are the operator's (`routing.watchdog`, `routing.asks`).
TICK_SECONDS = 30.0

#: Pastes ``prompt`` into a session; a :class:`~the_loop.runner.TmuxResult`.
Deliver = Callable[[Session, str], Any]
#: Hands one event to the channel bus. ``record=False`` keeps it off the ledger.
Publish = Callable[..., Any]
#: A node's facts from the graph definition, with ``command`` as the session
#: types it; ``{}`` for a node the graph does not have.
Resolve = Callable[[Session, str], Mapping[str, Any]]


# -- what the watcher types ---------------------------------------------------------


def nudge_text(
    *, node: str, command: str, minutes: int, ref: str, claim: str = ""
) -> str:
    """The nudge (R4.2): fixed prompt files, with the node, the command that
    resumes it, the idle minutes and the work item's own ref.

    ``claim`` is the work item's id when the node's exit is already met: the
    session is told to claim the node instead of resuming it.
    """
    lines = [prompts.render("watchdog/nudge", inline=True, minutes=minutes, node=node)]
    if claim:
        lines.append(prompts.render("watchdog/claim", inline=True, item_id=claim))
    elif command:
        lines.append(prompts.render("stopcheck/resume", inline=True, command=command))
    # The stop check's own words for the three ways out: one wording of them.
    lines.append(prompts.render("stopcheck/ways-out", inline=True, ref=ref))
    return "\n".join(lines)


_BACKTICKS = re.compile(r"`+")


def default_text(*, ref: str, default: str) -> str:
    """The "proceed with your default" message (R6.2).

    The default is the session's own earlier text. It is quoted inside a fence
    one backtick longer than any run in it, so nothing in it can close the
    fence and read as the-loop's words.
    """
    longest = max((len(run) for run in _BACKTICKS.findall(default)), default=0)
    return prompts.render(
        "watchdog/default-taken",
        inline=True,
        ref=ref,
        default=default,
        fence="`" * max(3, longest + 1),
    )


# -- one cycle ------------------------------------------------------------------------


def run_cycle(
    *,
    now: datetime,
    registry: SessionRegistry,
    log_path: Union[str, Path],
    watchdog: WatchdogConfig,
    asks: AsksConfig,
    deliver: Deliver,
    publish: Publish,
    resolve: Resolve,
) -> None:
    """Derive every live session's state and perform what it owes.

    The log is read once, however many sessions are live. A pull request's own
    endpoint is judged on its own ref, beside its work item's session: it gets
    the notice, the end of a stall and its asks' deadlines, and no nudge. One
    session's failure is logged and the others are still served.
    """
    grouped = sessionstate.load(log_path)
    for record in registry.list_sessions():
        if not record.is_live:
            continue
        for endpoint in (record, *record.pull_requests):
            if not endpoint.is_live:
                continue
            # Only this endpoint's own records: a session bound to another work
            # item is never judged, and so never typed to, on this one's log.
            events = grouped.get(endpoint.work_item.ref)
            if not events:
                continue
            try:
                state = sessionstate.derive(
                    events,
                    now=now,
                    watchdog=watchdog,
                    asks=asks,
                    work_item=endpoint.work_item.ref,
                )
                cycle = _Cycle(
                    endpoint=endpoint,
                    held=record.is_paused or endpoint.is_paused,
                    state=state,
                    events=events,
                    now=now,
                    deliver=deliver,
                    publish=publish,
                    # A pull request's own session walks the inner loop, and
                    # the node facts read here are the outer loop's. Its node
                    # stays unresolved: it gets the notice, and is never typed
                    # the command of a graph it is not on (fail closed).
                    resolve=resolve if endpoint is record else _unresolved,
                )
                for due in state.due:
                    cycle.perform(due)
            except Exception:  # noqa: BLE001 — one session never stops the rest
                logger.exception(
                    "the watcher's cycle failed for %s; continuing",
                    endpoint.work_item.ref,
                )


def _unresolved(endpoint: Session, node: str) -> Mapping[str, Any]:
    return {}


class _Cycle:
    """One session's acts in one cycle. Each act writes its record before it
    tells a channel, so a bus that fails costs a message and never a repeat."""

    def __init__(
        self,
        *,
        endpoint: Session,
        held: bool,
        state: SessionState,
        events: List[Dict[str, Any]],
        now: datetime,
        deliver: Deliver,
        publish: Publish,
        resolve: Resolve,
    ) -> None:
        self.endpoint = endpoint
        self.ref = endpoint.work_item.ref
        #: Paused: delivery is held, and a person chose that.
        self.held = held
        self.state = state
        self.events = events
        self.now = now
        self._deliver = deliver
        self._publish = publish
        self._resolve = resolve
        self._notified = state.notified

    def perform(self, due: Due) -> None:
        if due.act == "end-stall":
            self._end_stall(due)
        elif due.act == "nudge":
            self._nudge(due)
        elif due.act == "notify":
            self._notify(due)
        elif due.act == "take-default":
            self._take_default(due)
        elif due.act == "remind":
            self._remind(due)

    # -- the session's side ---------------------------------------------------------

    def _reachable(self) -> bool:
        """A session the daemon drives and may type to: it has a pane of the
        daemon's and nobody paused it (design § Fail-closed)."""
        return bool(self.endpoint.tmux_target) and not self.held

    def _paste(self, text: str) -> Any:
        try:
            return self._deliver(self.endpoint, text)
        except Exception as exc:  # noqa: BLE001 — a paste that raises did not land
            logger.warning("the watcher could not paste into %s: %s", self.ref, exc)
            return None

    def _tell(self, event: Event, record: Optional[bool] = None) -> None:
        try:
            self._publish(event, record=record)
        except Exception:  # noqa: BLE001 — the act is recorded; the bus is best effort
            logger.exception("could not publish %s for %s", event.event_type, self.ref)

    def _idle_seconds(self) -> int:
        since = sessionstate.parse_ts(self.state.idle_since)
        return max(0, int((self.now - since).total_seconds())) if since else 0

    # -- the acts -------------------------------------------------------------------

    def _nudge(self, due: Due) -> None:
        state = self.state
        if not self._reachable() or not state.node:
            return
        facts = dict(self._resolve(self.endpoint, state.node) or {})
        if not facts:
            # A stall whose node cannot be resolved gets the notice instead.
            return self._notify(due)
        if facts.get("actor") != "agent" or facts.get("terminal"):
            return  # nobody owes agent work here (R4.1)
        text = nudge_text(
            node=state.node,
            command=str(facts.get("command") or ""),
            minutes=self._idle_seconds() // 60,
            ref=self.ref,
            claim=(
                core_graphs.work_item_id(self.ref) if state.reason == "exit-met" else ""
            ),
        )
        result = self._paste(text)
        if result is not None and getattr(result, "session_missing", False):
            # No live pane: nothing was typed, and a person is told instead.
            return self._notify(due)
        # A paste that failed is recorded too: it spends the node visit's
        # budget, so a pane that never takes one is not tried without end.
        eventlog.emit(
            "session.nudged",
            work_item=self.ref,
            stall_id=due.stall_id,
            node=state.node,
            nudge=state.nudges_spent + 1,
            delivered=bool(result is not None and result.ok),
        )

    def _notify(self, due: Due) -> None:
        if not self._reachable() or self._notified:
            return
        self._notified = True
        state = self.state
        eventlog.emit(
            "session.stalled",
            work_item=self.ref,
            stall_id=due.stall_id,
            node=state.node or None,
            idle_since=state.idle_since,
        )
        self._tell(
            sessionnotes.stalled(
                self.ref,
                stall_id=due.stall_id or "",
                node=state.node,
                idle_seconds=self._idle_seconds(),
                nudges=state.nudges_spent,
                tmux_target=self.endpoint.tmux_target,
            )
        )

    def _end_stall(self, due: Due) -> None:
        acts = [r for r in self.events if r.get("stall_id") == due.stall_id]
        notified = any(r.get("event") == "session.stalled" for r in acts)
        node = next((str(r["node"]) for r in acts if r.get("node")), "")
        eventlog.emit(
            "session.stall_ended",
            work_item=self.ref,
            stall_id=due.stall_id,
            idle_seconds=due.idle_seconds,
        )
        # The id is the work item and the idle period's start.
        began = sessionstate.parse_ts((due.stall_id or "").rpartition("@")[2])
        ended = (
            began + timedelta(seconds=due.idle_seconds)
            if began is not None and due.idle_seconds is not None
            else None
        )
        self._tell(
            sessionnotes.stall_ended(
                self.ref,
                stall_id=due.stall_id or "",
                node=node,
                began=began,
                ended=ended,
                notified=notified,
            ),
            # A stall nobody was told about ends without a word on the ticket.
            record=notified,
        )

    def _asked(self, ask_id: Optional[str]) -> Dict[str, Any]:
        """The ask's own record, for the link to the question."""
        for record in reversed(self.events):
            if record.get("event") == "session.awaiting_input" and ask_id in (
                record.get("ask_id"),
                record.get("ts"),
            ):
                return record
        return {}

    def _take_default(self, due: Due) -> None:
        ask = self.state.open_ask
        # Fail closed: the derivation owes this only for a default with a
        # readable time, and it is checked again before anything is typed.
        if ask is None or ask.ask_id != due.ask_id or not ask.default:
            return
        if sessionstate.parse_ts(ask.default_at) is None:
            return
        result = (
            self._paste(default_text(ref=self.ref, default=ask.default))
            if self._reachable()
            else None
        )
        # Recorded whether or not the session could be told: the ask closes
        # exactly once (R6.10), and the thread says what happened.
        eventlog.emit(
            "session.ask_default_taken",
            work_item=self.ref,
            ask_id=ask.ask_id,
            default=ask.default,
            delivered=bool(result is not None and result.ok),
        )
        self._tell(
            sessionnotes.default_taken(
                self.ref,
                ask_id=ask.ask_id,
                default=ask.default,
                deadline=sessionstate.parse_ts(ask.default_at),
                question_url=str(self._asked(ask.ask_id).get("comment_url") or ""),
            )
        )

    def _remind(self, due: Due) -> None:
        ask = self.state.open_ask
        if ask is None or ask.ask_id != due.ask_id:
            return
        eventlog.emit("session.ask_reminded", work_item=self.ref, ask_id=ask.ask_id)
        asked = sessionstate.parse_ts(ask.asked_at)
        self._tell(
            sessionnotes.reminded(
                self.ref,
                ask_id=ask.ask_id,
                waited_seconds=(
                    max(0, int((self.now - asked).total_seconds())) if asked else 0
                ),
                question_url=str(self._asked(ask.ask_id).get("comment_url") or ""),
            )
        )


# -- the thread -------------------------------------------------------------------------


def _node(endpoint: Session, node: str) -> Dict[str, Any]:
    """``node``'s facts from the graph definition in the session's checkout,
    with the command as the stop check words it; ``{}`` when it cannot be read."""
    try:
        facts = core_graphs.node_facts(endpoint.cwd, endpoint.work_item.ref, node)
    except Exception as exc:  # noqa: BLE001 — a node that cannot be read is unknown
        logger.debug("cannot read node %s of %s: %s", node, endpoint.work_item.ref, exc)
        return {}
    if not facts:
        return {}
    return {**facts, "command": stopcheck._resume_command(facts, endpoint.work_item)}


def _cycle(config: Optional[dict]) -> None:
    """One cycle over what ``config`` names: the service's registry, its event
    log, the tmux paste path and the channel bus it already has."""
    from ..channels.bus import publish as bus_publish
    from ..runner import TmuxRunner

    routing = core_sessions._routing(config)
    run_cycle(
        now=datetime.now(timezone.utc),
        registry=SessionRegistry(core_sessions._registry_dir(config)),
        log_path=sessionsurface.log_path(config),
        watchdog=WatchdogConfig.from_mapping(routing.get("watchdog") or {}),
        asks=AsksConfig.from_mapping(routing.get("asks") or {}),
        deliver=TmuxRunner().deliver,
        publish=lambda event, record=None: bus_publish(
            event, dict(config or {}), record=record
        ),
        resolve=_node,
    )


_LOCK = threading.Lock()
#: The one watcher of this process. Two would each see an act as owed in the
#: moment before either recorded it, and type it twice.
_RUNNING: Optional[threading.Thread] = None


def start_watcher(
    cli_config: Optional[Mapping[str, Any]], stop_event: threading.Event
) -> Optional[threading.Thread]:
    """The service's hook (R4.11): the watcher's thread, or ``None`` when this
    process already runs one.

    The other watchers' shape exactly: a daemon thread looping
    ``stop_event.wait(TICK_SECONDS)`` → one cycle; the caller's stop event ends
    it, and a cycle that raises is logged and the next tick runs. Started
    whatever the config says: `routing.watchdog.enabled: false` stops the
    nudges and the notice, not the asks' deadlines or the end of a stall.
    """
    global _RUNNING
    frozen = dict(cli_config or {})

    def run() -> None:
        while not stop_event.wait(TICK_SECONDS):
            try:
                _cycle(frozen)
            except Exception:  # noqa: BLE001 — never kill the service over a tick
                logger.exception("the watcher's cycle raised; continuing")

    with _LOCK:
        if _RUNNING is not None and _RUNNING.is_alive():
            return None
        thread = threading.Thread(target=run, name="the-loop-watchdog", daemon=True)
        thread.start()
        _RUNNING = thread
    logger.info("the watcher looks at every session each %ss", TICK_SECONDS)
    return thread
