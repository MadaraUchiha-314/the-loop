"""Shared fixtures and doubles for the CLI test suite."""

import os
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Optional

import pytest

from the_loop import eventlog
from the_loop.announce import SessionAnnouncer
from the_loop.client.routing import SERVICE_LOCAL_ENV
from the_loop.control import ControlStore
from the_loop.graphlink import GraphLink
from the_loop.harness import HarnessAdapter
from the_loop.runner import SESSION_ABSENT, TmuxResult, TmuxRunner
from the_loop.sessions import SessionRegistry
from the_loop.trust import TrustResult
from the_loop.webhook import dispatcher as dispatcher_mod
from the_loop.webhook.router import Deduper

#: Every write the dispatcher makes **after** the spawn or delivery it was asked
#: for — the outcome of a dispatch, as opposed to the attempt that `FakeTmux`
#: records. ``--dispatch-lag`` delays exactly these, because a test that waits on
#: the attempt and then depends on the outcome is the shape issue-251 exists to
#: find (five instances so far, each failing about one run in three under load).
_DISPATCH_OUTCOME_WRITES = (
    (SessionRegistry, "register"),
    (SessionRegistry, "touch"),
    (SessionRegistry, "save_endpoint"),
    (SessionRegistry, "link_pull_request"),
    (SessionRegistry, "close"),
    (Deduper, "discard"),
    (SessionAnnouncer, "announce"),
    (GraphLink, "on_spawn"),
    (GraphLink, "on_event"),
    (ControlStore, "record"),
)


def _state_with_stores(path):
    """The channel state as the bot itself reads it (issue-368).

    A binding lives in its work item's portable record and a read cursor in its
    session record, so a test that wants to see what the bot wrote has to load
    the file **with** the stores beside it — loading the bare path shows only
    what belongs to no work item, which is the point of the split.
    """
    from the_loop.channels.state import ChannelState, ChannelStores

    return ChannelState.load(path, ChannelStores.beside(path))


def _freeze_legacy_graph(store, work_item, frozen: dict) -> None:
    """Write a portable record's `graph` section — the **pre-issue-368** shape.

    Nothing in the-loop writes this section any more: which phases a work item
    walks, the surface it is iterated on, how many sessions its pull requests
    get and what it runs on are all recorded in the work item's own checked-in
    `work-item-state.json`. It is still *read*, so a work item frozen before the
    change keeps its routing across the upgrade — and this helper is how a test
    sets up exactly that work item.
    """
    from the_loop.workitem import GRAPH

    store.store.write_section(work_item, GRAPH, dict(frozen))


#: The state trees no test may write into (issue-422): this repository's own
#: `.the-loop/` — its checked-in config and tracked `portable/` records — and the
#: `.the-loop/` of the directory pytest was started from, which is where every
#: cwd-relative default (`RoutingConfig.portable_dir`, `StateLayout()`) lands. A
#: test that needs a state root gives it one under `tmp_path`.
_PROTECTED_STATE = tuple(
    {
        os.path.join(os.path.abspath(p), "")
        for base in (Path(__file__).resolve().parents[2], Path.cwd())
        for p in (base / ".the-loop", (base / ".the-loop").resolve())
    }
)
#: The frames a report keeps: the-loop's own code and its tests, not the stdlib.
_CLI_DIR = str(Path(__file__).resolve().parents[1])
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
#: Per audit event, `(path index, dir_fd index)` for each path it changes. A
#: rename changes both ends; a link only its destination, never its target.
_PATH_ARGS = {
    "os.rename": ((0, 2), (1, 3)),
    "os.link": ((1, 3),),
    "os.symlink": ((1, 2),),
    "os.mkdir": ((0, 2),),
    "os.remove": ((0, 1),),
    "os.rmdir": ((0, 1),),
}
#: `(event, path, where)` for each write into a protected tree, drained by
#: `_no_protected_state_writes` after every test.
_protected_writes: list = []


def _protected(path) -> bool:
    if not isinstance(path, (str, bytes, os.PathLike)):
        return False  # an fd: whatever it points at was opened, and checked, by path
    try:
        absolute = os.path.abspath(os.fsdecode(path))
    except (OSError, ValueError):  # a deleted cwd: nothing can resolve against it
        return False
    return os.path.join(absolute, "").startswith(_PROTECTED_STATE)


def _audit_state_writes(event, args):
    """Record a write into a protected state tree, with the code that made it.

    An audit hook rather than a before/after snapshot because it names the test
    and the line, and because a daemon an operator runs from this checkout
    writes the same tree legitimately. It sees this process only: a test's
    subprocess is not covered. It must never raise: an exception in an audit
    hook propagates into the operation that was audited.
    """
    if event == "open":
        flags = args[2]
        paths = (args[0],) if isinstance(flags, int) and flags & _WRITE_FLAGS else ()
    elif event in _PATH_ARGS:
        # A name beside a dir_fd is relative to that directory, not the cwd:
        # `shutil.rmtree` removes a tmp tree's own `.the-loop/` that way.
        paths = tuple(
            args[path]
            for path, dir_fd in _PATH_ARGS[event]
            if args[dir_fd] in (None, -1)
        )
    else:
        return
    for path in paths:
        if _protected(path):
            frames = [
                f
                for f in traceback.extract_stack()[:-1]
                if f.filename.startswith(_CLI_DIR)
            ]
            where = "".join(traceback.format_list(frames[-6:]))
            _protected_writes.append((event, os.fsdecode(path), where))


sys.addaudithook(_audit_state_writes)


def _protected_write_report() -> str:
    writes = list(_protected_writes)
    _protected_writes.clear()
    return "\n".join(f"{event} {path}\n{where}" for event, path, where in writes)


@pytest.fixture(autouse=True)
def _no_protected_state_writes():
    """Fail the test that wrote into this repository's or the cwd's `.the-loop/`.

    Run from the repository root, a cwd-relative default resolves to the
    checked-in tree, and the write is silent: nothing fails, the tree is just
    dirty, and a staged-everything commit carries test debris in (issue-422).
    A write from a background thread that outlives its test is reported by
    the next one — the stack still names the code.
    """
    _protected_writes.clear()
    yield
    report = _protected_write_report()
    if report:
        pytest.fail(
            "wrote into a protected `.the-loop/` state tree — give the code "
            "under test a state root under tmp_path (issue-422):\n" + report,
            pytrace=False,
        )


def pytest_sessionfinish(session):
    """The writes no test's teardown saw: from a thread that outlived the last."""
    report = _protected_write_report()
    if report:
        session.config.get_terminal_writer().line(
            "\nwrote into a protected `.the-loop/` state tree after the last "
            "test (issue-422):\n" + report,
            red=True,
        )
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_addoption(parser):
    """``--dispatch-lag=<seconds>``: turn a wait-ordering flake into a certainty.

    Load is what used to expose these — the ticket measured one failure in three
    after ~16 seconds of unrelated wall-clock — so the suite carries its own load
    instead of waiting for a busy CI runner to supply some. See
    ``skills/the-loop/reference/testing.md`` § RULE: an asynchronous test waits on
    the state it depends on.
    """
    parser.addoption(
        "--dispatch-lag",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help=(
            "delay every dispatcher write that FOLLOWS a spawn or delivery "
            "(registry, deduper, announcer, graph link, control store) by this "
            "many seconds, so a test waiting on the attempt rather than its "
            "outcome fails every run instead of one in three. 0 disables."
        ),
    )


@pytest.fixture(autouse=True)
def _dispatch_lag(request, monkeypatch):
    """Widen the gap between a dispatch's attempt and its outcome (issue-251).

    Off unless asked for: at the default this is one float comparison per test and
    nothing is patched. When it is on, the patches go through ``monkeypatch``, so
    each unwinds at the end of its own test and no lagged class survives into the
    next one.
    """
    lag = request.config.getoption("--dispatch-lag")
    if lag <= 0:
        return
    for cls, name in _DISPATCH_OUTCOME_WRITES:
        real = getattr(cls, name)

        def slow(self, *args, _real=real, **kwargs):
            time.sleep(lag)
            return _real(self, *args, **kwargs)

        monkeypatch.setattr(cls, name, slow)


@pytest.fixture(autouse=True)
def _local_execution(monkeypatch, request):
    """Run command tests on the local execution path (issue-161).

    The service-only rule routes core-capability commands through the
    control-plane service. The in-process path runs the *same* core facade the
    service calls, so covering it here is behaviour coverage without standing a
    server up per test. Routed-transport tests opt out with the ``routed``
    marker and exercise a real service end-to-end
    (test_service_lifecycle_integration.py).
    """
    if "routed" in request.keywords:
        monkeypatch.delenv(SERVICE_LOCAL_ENV, raising=False)
    else:
        monkeypatch.setenv(SERVICE_LOCAL_ENV, "1")


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


class _NoopVerifier:
    """Stand-in for WorkItemVerifier that never shells out.

    Answers "unknown" (issue-269's fail-open direction), so a dispatcher test
    that never heard of the existence check routes exactly as it did before it.
    """

    def __init__(self, *args, **kwargs):
        pass

    def is_missing(self, item):
        return False

    def record_missing(self, item):
        return None


@pytest.fixture(autouse=True)
def _hermetic_reactor(monkeypatch):
    """Dispatchers built without injected gh-writers must not shell out to gh.

    ``routing.reactions`` (issue-84) and ``routing.announce`` (issue-86) both
    default to enabled, so a bare ``RoutingConfig()`` would give every
    dispatcher test a real ``GitHubReactor``/``SessionAnnouncer`` — and CI
    runners ship a real ``gh``. The work-item existence check (issue-269) reads
    through the same binary. Stub the classes the dispatcher instantiates; the
    reaction/announcement/linkage tests inject their own.
    """
    monkeypatch.setattr(dispatcher_mod, "GitHubReactor", _NoopReactor)
    monkeypatch.setattr(dispatcher_mod, "SessionAnnouncer", _NoopAnnouncer)
    monkeypatch.setattr(dispatcher_mod, "WorkItemVerifier", _NoopVerifier)


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
