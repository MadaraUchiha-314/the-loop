"""A watcher's world for tests (issue-551): a fake clock that also stamps the
event log, a session registry under ``tmp_path``, the recording tmux double and
a recording bus. Shared by the watchdog's unit and integration tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from conftest import FakeTmux
from the_loop import eventlog
from the_loop.core import sessionstate, watchdog
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.watchconfig import AsksConfig, WatchdogConfig

REF = "github:octo/repo#7"
TARGET = "loop-github-octo-repo-7"
T0 = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)

#: Short numbers so that a scenario reads in minutes.
WATCHDOG = WatchdogConfig(idle_seconds=600, max_nudges=2, max_wait_seconds=3600)
ASKS = AsksConfig(min_default_wait_seconds=1800, reminder_seconds=7200)

#: The graph definition's facts, as the watcher's resolver returns them.
NODES: Dict[str, Dict[str, Any]] = {
    "build": {"actor": "agent", "command": "/the-loop:execute-tasks issue-7"},
    "bare": {"actor": "agent", "command": ""},
    "gate": {"actor": "human", "command": ""},
}


class World:
    """Everything one cycle touches, with the clock in the test's hands."""

    def __init__(self, tmp_path, monkeypatch) -> None:
        self.minutes = 0.0
        self.log = tmp_path / "events.jsonl"
        eventlog.configure("test", path=self.log)
        monkeypatch.setattr(eventlog, "_utcnow", self.stamp)
        self._monkeypatch = monkeypatch
        self.registry = SessionRegistry(tmp_path / "sessions")
        self.tmux = FakeTmux()
        self.published: List[Tuple[Any, Optional[bool]]] = []
        #: Where the cycle publishes. A test that wants the real bus puts it
        #: here, with the comments its ledger wrote and the channels it fans to.
        self.publish: Any = lambda event, record=None: self.published.append(
            (event, record)
        )
        self.comments: List[str] = []
        self.channel: Any = None
        self.channels: List[Any] = []
        self.cwd = str(tmp_path)

    # -- the clock ----------------------------------------------------------------

    def now(self) -> datetime:
        return T0 + timedelta(minutes=self.minutes)

    def stamp(self, minutes: Optional[float] = None) -> str:
        moment = self.now() if minutes is None else T0 + timedelta(minutes=minutes)
        return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def at(self, minutes: float) -> "World":
        self.minutes = minutes
        return self

    # -- the session and what it records ---------------------------------------------

    def register(self, ref: str = REF, target: str = TARGET) -> Session:
        return self.registry.register(
            Session(
                work_item=WorkItemRef.parse(ref),
                harness="claude",
                harness_session_id="sess-1",
                cwd=self.cwd,
                tmux_target=target,
            )
        )

    def emit(self, minutes: float, event: str, ref: str = REF, **fields) -> None:
        self.at(minutes)
        eventlog.emit(event, work_item=ref, **fields)

    def started(self, minutes: float, node: str = "build", ref: str = REF) -> None:
        self.emit(minutes, "session.turn_started", ref, node=node)

    def ended(
        self,
        minutes: float,
        reason: str = "gate-gave-up",
        node: Optional[str] = "build",
        ref: str = REF,
    ) -> None:
        self.emit(
            minutes,
            "session.turn_ended",
            ref,
            node=node,
            node_status="block",
            reason=reason,
        )

    def records(self, event: str) -> List[Dict[str, Any]]:
        return [r for r in eventlog.read_events(self.log) if r.get("event") == event]

    # -- the watcher -----------------------------------------------------------------

    def cycle(
        self,
        minutes: Optional[float] = None,
        watchdog_config: WatchdogConfig = WATCHDOG,
        asks: AsksConfig = ASKS,
    ) -> None:
        """One tick, built from nothing but the log and the registry: every
        call is a brand-new watcher, which is what a restart is."""
        if minutes is not None:
            self.at(minutes)
        watchdog.run_cycle(
            now=self.now(),
            registry=self.registry,
            log_path=self.log,
            watchdog=watchdog_config,
            asks=asks,
            deliver=self.tmux.deliver,
            publish=self.publish,
            resolve=lambda endpoint, node: dict(NODES.get(node) or {}),
        )

    def after_the_snapshot(self, happens: Callable[[], None]) -> None:
        """Run ``happens`` once, right after the next cycle has read the whole
        log and before it performs anything: what another thread or process
        wrote while the watcher was busy with an earlier session."""
        real = sessionstate.load
        pending = [happens]

        def load(path, work_item=None):
            grouped = real(path, work_item=work_item)
            if work_item is None and pending:
                pending.pop()()
            return grouped

        self._monkeypatch.setattr(sessionstate, "load", load)

    def pasted(self) -> List[str]:
        return [prompt for _, prompt in self.tmux.delivers]

    def published_types(self) -> List[str]:
        return [event.event_type for event, _ in self.published]
