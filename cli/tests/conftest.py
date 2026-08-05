"""Shared fixtures and doubles for the CLI test suite."""

import threading
import time
import uuid
from typing import Optional

import pytest

from the_loop import eventlog
from the_loop.harness import HarnessAdapter
from the_loop.runner import SESSION_ABSENT, TmuxResult, TmuxRunner
from the_loop.trust import TrustResult
from the_loop.webhook import dispatcher as dispatcher_mod


class StubInteractiveAdapter(HarnessAdapter):
    """Minimal HarnessAdapter double for tmux spawns (argv never executed)."""

    name = "claude"
    default_binary = "claude-stub"

    def is_available(self):
        return True

    def prepare_environment(self, cwd, root=None):
        return TrustResult()

    def interactive_argv(self, prompt, session_id):
        return ["--session-id", session_id, prompt]

    def interactive_resume_argv(self, prompt, session_id):
        return ["--resume", session_id, prompt]


class FakeTmux(TmuxRunner):
    """In-process TmuxRunner double: records deliveries/spawns, all succeed.

    Since the process runner's removal (issue-156) every dispatch goes through
    the tmux runner, so dispatcher tests observe *this* seam instead of a fake
    adapter's ``resume``/``spawn``. ``delivers``/``spawns`` mirror the shapes
    the old FakeAdapter recorded; the concurrency accounting
    (``max_in_flight``) is kept so the serialization tests still measure it.
    Knobs: ``session_missing`` fails every delivery as "session gone" (driving
    the respawn path); ``deliver_ok=False`` fails it transiently;
    ``deliver_gate`` (a ``threading.Event``) wedges every delivery until it is
    set, which is how a test gets an event to sit in a worker's queue — set it
    in a ``finally`` so no thread is left blocked (issue-159).
    """

    def __init__(self, delay=0.0):
        super().__init__(binary="tmux-double-never-run")
        self.delay = delay
        self.deliver_gate: Optional[threading.Event] = None
        self.delivers = []  # (work_item_ref, prompt)
        self.spawns = []  # (work_item_ref, prompt, cwd, resume)
        self.kills = []
        self.terminated = []
        self.remain_on_exit = True
        self.deliver_ok = True
        self.session_missing = False
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0

    def is_available(self):
        return True

    def target_for(self, work_item):
        return f"loop-{work_item.slug}"

    def session_state(self, target):
        return SESSION_ABSENT

    def has_session(self, target):
        return False

    def has_live_session(self, target):
        return True

    def survived(self, target, delay, sleeper=time.sleep):
        return True

    def live_pane_pids(self, target):
        return []

    def deliver(self, session, prompt, timeout=None):
        with self._lock:
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            if self.delay:
                time.sleep(self.delay)
            if self.deliver_gate is not None:
                self.deliver_gate.wait(timeout=30)
            if self.session_missing:
                return TmuxResult(
                    ok=False, session_missing=True, error="tmux session gone"
                )
            with self._lock:
                self.delivers.append((session.work_item.ref, prompt))
            if not self.deliver_ok:
                return TmuxResult(ok=False, error="paste failed")
            return TmuxResult(ok=True)
        finally:
            with self._lock:
                self._in_flight -= 1

    def spawn(
        self,
        work_item,
        adapter,
        prompt,
        cwd,
        session_id,
        timeout=None,
        resume=False,
    ):
        with self._lock:
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            if self.delay:
                time.sleep(self.delay)
            with self._lock:
                self.spawns.append((work_item.ref, prompt, cwd, resume))
            return TmuxResult(ok=True)
        finally:
            with self._lock:
                self._in_flight -= 1

    def terminate_harness(
        self, session, grace=5.0, timeout=None, sleeper=time.sleep, killer=None
    ):
        self.terminated.append(session.tmux_target)
        return TmuxResult(ok=True)

    def kill(self, session, timeout=None):
        self.kills.append(session.tmux_target)
        return TmuxResult(ok=True)


def fresh_session_id():
    """A uuid-shaped id like the ones the dispatcher pre-assigns."""
    return str(uuid.uuid4())


class _NoopReactor:
    """Stand-in for GitHubReactor that never shells out."""

    def __init__(self, *args, **kwargs):
        pass

    def react(self, routed, state):
        return False


class _NoopAnnouncer:
    """Stand-in for SessionAnnouncer that never shells out."""

    def __init__(self, *args, **kwargs):
        pass

    def announce(self, session):
        return False


@pytest.fixture(autouse=True)
def _hermetic_reactor(monkeypatch):
    """Dispatchers built without injected gh-writers must not shell out to gh.

    ``routing.reactions`` (issue-84) and ``routing.announce`` (issue-86) both
    default to enabled, so a bare ``RoutingConfig()`` would give every
    dispatcher test a real ``GitHubReactor``/``SessionAnnouncer`` — and CI
    runners ship a real ``gh``. Stub the classes the dispatcher instantiates;
    the reaction/announcement tests inject their own.
    """
    monkeypatch.setattr(dispatcher_mod, "GitHubReactor", _NoopReactor)
    monkeypatch.setattr(dispatcher_mod, "SessionAnnouncer", _NoopAnnouncer)


@pytest.fixture(autouse=True)
def _hermetic_eventlog(monkeypatch):
    """Keep the process-wide event log out of the real working tree.

    CLI entry points call ``eventlog.configure_from_file`` which resolves a
    cwd-relative default path — under test that would append a real
    ``.the-loop/logs/events.jsonl`` into the repo. Stub it to a disabled log;
    tests that assert on the log configure their own tmp path explicitly.
    """
    eventlog.reset()
    monkeypatch.setattr(
        eventlog,
        "configure_from_file",
        lambda source: eventlog.configure(source, enabled=False),
    )
    yield
    eventlog.reset()
