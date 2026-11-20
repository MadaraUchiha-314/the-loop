"""The idle watchdog, end to end (issue-551, testing-plan T4).

The shipped hook scripts, the real control-plane service, the real event log and
the real watcher cycle in one run, with a stub harness (`stub_harness.py`) in a
real tmux pane standing where Claude Code stands.

    stub harness ──hook scripts──► the-loop CLI ──HTTP──► service ──► event log
          ▲                                                              │
          └────────── tmux paste ◄── TmuxRunner ◄── watchdog.run_cycle ◄─┘

**Isolation.** This machine may run a live daemon and live `loop-*` tmux
sessions, and nothing here may reach them:

* tmux — a server of the test's own on a private socket (`tmux -L <unique>`).
  Every tmux call, the watcher's included, goes through one shim that carries
  the `-L`; the server is killed in a finalizer.
* the service — a process of the test's own on a free loopback port, with a
  config, a state root, a registry and an event log under ``tmp_path``. It is
  asked which config and state root it runs on before anything else happens.
* the environment — every child gets one built from scratch here: no
  ``THE_LOOP_*`` or ``TMUX*`` variable of the surrounding shell survives.

The clock is the test's only fake: every record is stamped by the process that
writes it, and the watcher is asked what it owes at a moment the test moves
forward, one idle threshold at a time.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

from the_loop import eventlog
from the_loop.api.config import DEFAULT_PORT
from the_loop.cli_config import load_cli_config
from the_loop.core import sessionsurface, watchdog
from the_loop.runner import TmuxRunner
from the_loop.sessions.registry import Session, SessionRegistry
from the_loop.state import layout_from_config
from the_loop.watchconfig import AsksConfig, WatchdogConfig
from the_loop.workitem import WorkItemRef
from test_gate_pointer_integration import (
    PAST_AN_APPROVED_GATE,
    REF,
    REQUIREMENTS,
    WORK_ITEM,
    _checkout,
)

TESTS = Path(__file__).resolve().parent
HOOKS = TESTS.parents[1] / "hooks"
STUB = TESTS / "stub_harness.py"

#: The Stop hook's own cap: this many refusals, then the stop is let through.
GATE_ATTEMPTS = 2
IDLE_SECONDS = 600
WATCHDOG = WatchdogConfig(idle_seconds=IDLE_SECONDS, max_nudges=2)
ASKS = AsksConfig()

#: How long one step may take. A stub turn is a handful of CLI start-ups.
STEP_TIMEOUT_SECONDS = 60.0

pytestmark = [
    pytest.mark.skipif(
        shutil.which("tmux") is None,
        reason="tmux is not on PATH: the end-to-end run needs a real pane (T4)",
    ),
]


def _until(what: str, probe: Callable[[], Any], world: "World") -> Any:
    """``probe()``'s first truthy value, polled; fails with the pane's text."""
    deadline = time.monotonic() + STEP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        value = probe()
        if value:
            return value
        time.sleep(0.05)
    pytest.fail(f"timed out waiting for {what}\n{world.diagnostics()}")


class World:
    """The test's own tmux server, service, state root and clock."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        tag = uuid.uuid4().hex[:8]
        #: Private to this run. Never the default socket, where `loop-*` live.
        self.socket = f"the-loop-e2e-551-{tag}"
        #: Not `loop-…`: no name a daemon's session could have.
        self.target = f"e2e-551-{tag}"
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        self.repo = _checkout(tmp_path / "checkout", PAST_AN_APPROVED_GATE)
        (self.repo / "docs" / "specs" / WORK_ITEM / "requirements.md").write_text(
            REQUIREMENTS
        )
        self.state_root = tmp_path / ".the-loop"
        self.transcript = tmp_path / "transcript.jsonl"
        self.service_log = tmp_path / "service.log"
        self.port = self._free_port()
        self.config_path = tmp_path / "cli-config.yaml"
        self.config_path.write_text(
            'version: "0.12.0"\n'
            f'state:\n  root: "{self.state_root}"\n'
            "service:\n"
            '  host: "127.0.0.1"\n'
            f"  port: {self.port}\n"
            # A CLI that finds no service must fail, never start another one.
            "  autoStart: false\n"
            "  mcp:\n    enabled: false\n"
        )
        self.config = load_cli_config(self.config_path)
        self.layout = layout_from_config(self.config)
        self.log = Path(sessionsurface.log_path(self.config))
        self.registry = SessionRegistry(self.layout.local_dir)
        self.tmux = self._shim(
            "tmux",
            "unset TMUX TMUX_PANE\n"
            f'exec "{shutil.which("tmux")}" -L {self.socket} -f /dev/null "$@"\n',
        )
        self._shim("the-loop", f'exec "{sys.executable}" -m the_loop "$@"\n')
        self.service: Any = None
        #: How far ahead of the wall clock the watcher is asked to look.
        self.ahead = timedelta(0)
        self.published: List[Any] = []

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    def _shim(self, name: str, body: str) -> Path:
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
        return path

    def env(self, **extra: str) -> Dict[str, str]:
        """A child's whole environment. Nothing of the surrounding shell that
        names a the-loop instance, a work item, a config or a tmux server."""
        kept = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith(("THE_LOOP_", "TMUX"))
        }
        return {
            **kept,
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}",
            "HOME": str(self.tmp),
            "TMPDIR": str(self.tmp),  # the gate's attempt counter stays here
            "THE_LOOP_CLI_CONFIG": str(self.config_path),
            **extra,
        }

    # -- bring-up and tear-down -------------------------------------------------------

    def start_service(self) -> Dict[str, Any]:
        assert self.port != DEFAULT_PORT
        with self.service_log.open("w") as out:
            self.service = subprocess.Popen(
                [sys.executable, "-m", "the_loop.api.serve"],
                cwd=self.tmp,
                env=self.env(),
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.STDOUT,
            )
        return _until("the test's own service", self.health, self)

    def health(self) -> Dict[str, Any]:
        if self.service.poll() is not None:
            pytest.fail(f"the service exited\n{self.diagnostics()}")
        try:
            url = f"http://127.0.0.1:{self.port}/api/v1/health"
            with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310
                return json.loads(response.read().decode())
        except OSError:
            return {}

    def start_stub(self) -> None:
        launcher = self._shim(
            "stub-harness",
            f'exec "{sys.executable}" "{STUB}" "{HOOKS}" "{self.transcript}"\n',
        )
        subprocess.run(
            [str(self.tmux), "new-session", "-d", "-s", self.target]
            + ["-x", "200", "-y", "50", "-c", str(self.repo), str(launcher)],
            env=self.env(
                THE_LOOP_WORK_ITEM=REF,
                THE_LOOP_GATE_MAX_ATTEMPTS=str(GATE_ATTEMPTS),
            ),
            check=True,
            capture_output=True,
            timeout=30,
        )

    def close(self) -> None:
        subprocess.run(
            [str(self.tmux), "kill-server"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        # tmux leaves a dead server's socket file behind. `env` hands tmux no
        # TMUX_TMPDIR, so this is where `-L` put it.
        Path(f"/tmp/tmux-{os.getuid()}", self.socket).unlink(missing_ok=True)
        if self.service is not None and self.service.poll() is None:
            self.service.terminate()
            try:
                self.service.wait(10)
            except subprocess.TimeoutExpired:
                self.service.kill()
                self.service.wait(10)

    def diagnostics(self) -> str:
        pane = subprocess.run(
            [str(self.tmux), "capture-pane", "-p", "-t", self.target],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        log = self.service_log.read_text() if self.service_log.exists() else ""
        events = [f"{r['ts']} {r['event']}" for r in self.records()]
        return (
            f"--- pane ---\n{pane.stdout or pane.stderr}\n"
            f"--- events ---\n"
            + "\n".join(events)
            + f"\n--- service ---\n{log[-3000:]}"
        )

    # -- what the run left behind -----------------------------------------------------

    def turns(self) -> List[Dict[str, Any]]:
        if not self.transcript.exists():
            return []
        lines = self.transcript.read_text().splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def turn(self, number: int) -> Dict[str, Any]:
        """The stub's finished turn ``number``, waited for."""
        return _until(
            f"the stub's turn {number}",
            lambda: next((t for t in self.turns() if t["turn"] == number), None),
            self,
        )

    def records(self, *events: str) -> List[Dict[str, Any]]:
        """The session's records in the log, oldest first."""
        return [
            record
            for record in eventlog.read_events(self.log)
            if record.get("work_item") == REF
            and record.get("event", "").startswith("session.")
            and (not events or record["event"] in events)
        ]

    def kinds(self) -> List[str]:
        return [record["event"] for record in self.records()]

    # -- the watcher ------------------------------------------------------------------

    def cycle(self) -> None:
        """One tick of a brand-new watcher, as `watchdog._cycle` builds it: the
        service's registry and log, the graph in the session's checkout and the
        real tmux paste path. The clock, the socket and the bus are the test's."""
        watchdog.run_cycle(
            now=datetime.now(timezone.utc) + self.ahead,
            registry=self.registry,
            log_path=self.log,
            watchdog=WATCHDOG,
            asks=ASKS,
            deliver=TmuxRunner(binary=str(self.tmux)).deliver,
            publish=lambda event, record=None: self.published.append(event),
            resolve=watchdog._node,
        )

    def pass_the_idle_threshold(self) -> None:
        self.ahead += timedelta(seconds=IDLE_SECONDS + 1)


@pytest.fixture
def world(tmp_path):
    world = World(tmp_path)
    try:
        # Before any pane exists: the service that answers is this test's own.
        health = world.start_service()
        assert Path(health["stateRoot"]) == world.state_root
        assert Path(health["configPath"]) == world.config_path
        world.registry.register(
            Session(
                work_item=WorkItemRef.parse(REF),
                harness="claude",
                harness_session_id="sess-e2e",
                cwd=str(world.repo),
                tmux_target=world.target,
            )
        )
        # The watcher's own records go where the service's do.
        eventlog.configure("watchdog-e2e", path=world.log)
        world.start_stub()
        yield world
    finally:
        eventlog.reset()
        world.close()


def test_an_idle_session_is_refused_nudged_reported_and_resumed(world):
    """A useless session, from its first refused stop to the end of its stall.

    Requirement: docs/specs/issue-551/requirements.md R3, R4, R4.11

    1. The stop is refused and names the node, past an approved human gate (R3).
    2. After the hook's cap the stop is allowed and recorded `gate-gave-up`.
    3. Past the idle threshold the watcher pastes the nudge into the pane, and
       the harness's turn-start hook records the turn it starts (R4.1, R4.2).
    4. The session stays useless: `maxNudges` nudges, one notice, nothing more.
    5. A prompt delivered for a person starts a turn, and the stall ends (R4.5).

    The service hosts no ingress throughout: the watcher needs none (R4.11).
    """
    ingresses = world.health()["ingresses"]
    assert ingresses and not any(row["enabled"] or row["running"] for row in ingresses)

    # 1. Refused, with the node, its unmet check and the command that resumes it.
    first = world.turn(0)
    refusals = [stop for stop in first["stops"] if stop["exit"] == 2]
    assert len(refusals) == GATE_ATTEMPTS
    for attempt, refused in enumerate(refusals, start=1):
        assert "Node `design` still owes work" in refused["stderr"]
        assert "design.md" in refused["stderr"]
        assert "/the-loop:create-design issue-1" in refused["stderr"]
        assert f"(attempt {attempt}/{GATE_ATTEMPTS})" in refused["stderr"]

    # 2. The cap lets the stop through, and the service records why.
    gave_up = first["stops"][-1]
    assert gave_up["exit"] == 0
    assert f"still incomplete after {GATE_ATTEMPTS} attempts" in gave_up["stderr"]
    (ended,) = _until(
        "the first turn's end", lambda: world.records("session.turn_ended"), world
    )
    assert (ended["node"], ended["node_status"]) == ("design", "block")
    assert ended["reason"] == "gate-gave-up"
    assert world.kinds() == ["session.turn_ended"], "a refusal records nothing"

    # 3. Nothing before the threshold; past it, the nudge is in the pane.
    world.cycle()
    assert world.kinds() == ["session.turn_ended"]
    world.pass_the_idle_threshold()
    world.cycle()
    nudged = world.turn(1)
    assert "idle for 10 minutes at node `design`" in nudged["prompt"]
    assert "/the-loop:create-design issue-1" in nudged["prompt"]
    assert f"the-loop ask --work-item {REF}" in nudged["prompt"]
    assert f"the-loop wait --work-item {REF}" in nudged["prompt"]
    assert world.kinds() == [
        "session.turn_ended",
        "session.nudged",
        "session.turn_started",  # the turn-start hook fired on the paste
        "session.turn_ended",
    ]
    (nudge,) = world.records("session.nudged")
    assert (nudge["node"], nudge["nudge"], nudge["delivered"]) == ("design", 1, True)
    assert world.records("session.turn_started")[0]["node"] == "design"

    # 4. An empty turn per nudge buys no new budget.
    world.pass_the_idle_threshold()
    world.cycle()
    world.turn(2)
    world.pass_the_idle_threshold()
    world.cycle()
    assert [r["nudge"] for r in world.records("session.nudged")] == [1, 2]
    (stalled,) = world.records("session.stalled")
    assert stalled["node"] == "design"
    assert [e.event_type for e in world.published if e.event_type == "session.stalled"]
    settled = world.kinds()
    for _ in range(4):
        world.pass_the_idle_threshold()
        world.cycle()
    assert world.kinds() == settled
    assert len(world.turns()) == 3, "nothing more was pasted"
    assert settled.count("session.nudged") == WATCHDOG.max_nudges
    assert settled.count("session.stalled") == 1
    assert settled.index("session.stalled") > max(
        i for i, kind in enumerate(settled) if kind == "session.nudged"
    )

    # 5. A person's event reaches the pane: a turn starts, and the stall ends.
    open_stall = stalled["stall_id"]
    assert open_stall not in [
        r["stall_id"] for r in world.records("session.stall_ended")
    ]
    delivered = TmuxRunner(binary=str(world.tmux)).deliver_to(
        world.target, "a reviewer commented:\nplease go on"
    )
    assert delivered.ok, delivered.error
    assert world.turn(3)["prompt"] == "a reviewer commented:\nplease go on"
    world.cycle()
    assert world.records("session.stall_ended")[-1]["stall_id"] == open_stall
    assert world.kinds()[-3:] == [
        "session.turn_started",
        "session.turn_ended",
        "session.stall_ended",
    ]
    assert world.published[-1].event_type == "session.stall_ended"
