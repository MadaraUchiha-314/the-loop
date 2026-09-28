"""The six lifecycle hook points, at their call sites (issue-344, T6/T7).

Feature: lifecycle hooks run where the thing they decide is about to happen
  A real Dispatcher with FakeTmux, a real graph Runtime over a tmp_path repository,
  and the real `ask_session` with a patched `gh` — driven by the same events the
  daemons produce, with the operator's hooks installed as an in-process runner.
"""

from __future__ import annotations

import time
from typing import Any, cast

import pytest

from conftest import FakeTmux, StubInteractiveAdapter
from the_loop import eventlog, lifecycle
from the_loop.channels import base as channels_base
from the_loop.channels.base import PostResult
from the_loop.control import ControlConfig, ControlStore
from the_loop.core import sessions as core_sessions
from the_loop.graph import hooks as _graph_hooks  # noqa: F401 — registers built-ins
from the_loop.graph.model import compile_graph
from the_loop.graph.runtime import Runtime
from the_loop.lifecycle.executors import LocalExecutor
from the_loop.lifecycle.runner import Runner
from the_loop.sdk.hooks import LifecycleHooks
from the_loop.sessions import SessionRegistry
from the_loop.webhook import dispatcher as dispatcher_mod
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent, extract_work_items

LABEL = "the-loop: auto-execute"
REF = "github:octo/repo#15"


class Recorder(LifecycleHooks):
    """Sees every point; the test scripts its decisions per point."""

    def __init__(self, **decide):
        self.seen = []
        self.decide = decide

    def _at(self, ctx):
        self.seen.append(ctx)
        changes: Any = self.decide.get(ctx.POINT)
        if callable(changes):
            changes = changes(ctx)
        if changes:
            for key, value in changes.items():
                setattr(ctx, key, value)
            return ctx
        return None

    work_item_start = _at
    session_spawn = _at
    session_spawned = _at
    waiting_for_input = _at
    phase_changed = _at
    work_item_complete = _at


def install(**decide) -> Recorder:
    hooks = Recorder(**decide)
    lifecycle.configure(Runner([LocalExecutor("test-hooks", hooks)]))
    return hooks


def points(hooks, name):
    return [ctx for ctx in hooks.seen if ctx.POINT == name]


@pytest.fixture
def events(tmp_path):
    path = tmp_path / "events.jsonl"
    eventlog.configure("test", path=path)
    yield lambda name=None: [
        e for e in eventlog.read_events(path) if name is None or e["event"] == name
    ]
    eventlog.reset()


@pytest.fixture
def comments(monkeypatch):
    posted = []
    monkeypatch.setattr(
        dispatcher_mod,
        "post_issue_comment",
        lambda item, body, gh_binary="gh": (
            posted.append((item.ref, body)) or (True, "")
        ),
    )
    return posted


class _Announcer:
    def __init__(self):
        self.announced = []

    def announce(self, session):
        self.announced.append(session.work_item.ref)
        return True


class _Link:
    """A graph link whose parked-ness the test decides; records nothing else."""

    def __init__(self, parked=False):
        self.parked = parked
        self.armed = 0

    def on_arm(self, work_item, cwd, routed=None):
        self.armed += 1
        return self.parked

    def context(self, work_item, cwd):
        return None

    def on_event(self, work_item, cwd, routed):
        return None

    def on_spawn(self, work_item, cwd, session_id="", runner="", routed=None):
        pass

    def on_close(self, work_item, cwd):
        pass

    def on_cleanup(self, work_item, cwd, reason=""):
        pass

    def on_pr_state(self, *args, **kwargs):
        pass


def _dispatcher(tmp_path, **overrides):
    registry = SessionRegistry(tmp_path / "local")
    tmux = FakeTmux()
    announcer = _Announcer()
    lifecycle_posts = []
    config = RoutingConfig(
        registry_dir=str(tmp_path / "local"),
        portable_dir=str(tmp_path / "portable"),
        spawn_on_unmatched="labeled",
        auto_execute_labels=[LABEL],
        spawn_workdir=str(tmp_path),
        control=ControlConfig(),
        authorized_users=["octocat"],
        **overrides,
    )
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=config,
        tmux_runner=tmux,
        announcer=announcer,  # type: ignore[arg-type] — a recording double
        lifecycle=lambda kind, ref, text, detail: lifecycle_posts.append((kind, ref)),
    )
    link = _Link()
    dispatcher.graphlink = link  # type: ignore[assignment] — the test decides parking
    store = ControlStore(str(tmp_path / "portable"))
    return dispatcher, registry, tmux, store, announcer, lifecycle_posts, link


def comment(body, delivery="d-1", author="octocat"):
    payload = {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15, "labels": [{"name": LABEL}]},
        "comment": {
            "id": 1,
            "body": body,
            "html_url": "https://c/1",
            "user": {"login": author},
        },
        "sender": {"login": author},
    }
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id=delivery,
        work_items=extract_work_items("issue_comment", payload),
        payload=payload,
    )


def closed(delivery="c-1"):
    payload = {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15, "labels": []},
        "sender": {"login": "octocat"},
    }
    return RoutedEvent(
        event="issues",
        action="closed",
        delivery_id=delivery,
        work_items=extract_work_items("issues", payload),
        payload=payload,
    )


def _wait(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


# ------------------------------------------------------------ work_item_start


def test_a_hook_refuses_a_start_and_the_work_item_is_disarmed_with_a_reason(
    tmp_path, events, comments
):
    """
    Feature: lifecycle hooks run where the thing they decide is about to happen
      Scenario: a hook refuses a start and the work item is disarmed with a reason on the ticket
        Given a work_item_start hook that refuses actors not on its roster
        When an authorized user arms the work item with `the-loop start`
        Then no session is spawned and the control record is cleared
        And one marked comment on the ticket names the hook's reason
        And hooks.refused is recorded and the delivery is settled, not retried

    Requirement: docs/specs/issue-344/requirements.md R2.6, R1.2
    """
    hooks = install(
        work_item_start={"proceed": False, "reason": "octocat is not on the roster"}
    )
    dispatcher, registry, tmux, store, announcer, _, _ = _dispatcher(tmp_path)
    dispatcher.handle(comment("the-loop start"))
    assert _wait(lambda: events("hooks.refused"))
    dispatcher.stop()

    assert tmux.spawns == []
    assert registry.find_by_work_item(REF) is None
    assert store.get(REF) is None, "a refused start leaves nothing armed"
    (start,) = points(hooks, "work_item_start")
    assert (start.work_item.ref, start.command, start.actor) == (
        REF,
        "start",
        "octocat",
    )
    assert (start.work_item.kind, start.work_item.repository) == ("issue", "octo/repo")
    assert start.work_item.url == "https://github.com/octo/repo/issues/15"
    assert start.loop == "pdlc-work-item-loop"
    assert start.harness == "claude"
    (ref, body) = comments[-1]
    assert (
        ref == REF
        and "not on the roster" in body
        and "<!-- the-loop:agent-comment -->" in body
    )
    (refused,) = events("hooks.refused")
    assert refused["point"] == "work_item_start" and refused["work_item"] == REF
    assert dispatcher.deduper.outcome("d-1") == "hook-refused"


def test_a_permitted_start_spawns_and_the_hook_saw_it_once(tmp_path, events):
    hooks = install()
    dispatcher, registry, tmux, store, announcer, _, _ = _dispatcher(tmp_path)
    dispatcher.handle(comment("the-loop start"))
    assert _wait(lambda: tmux.spawns)
    dispatcher.stop()
    assert len(points(hooks, "work_item_start")) == 1
    assert store.get(REF) is not None
    assert events("hooks.refused") == []


def test_work_item_start_fires_once_across_a_deferred_spawn(tmp_path):
    """
    Feature: lifecycle hooks run where the thing they decide is about to happen
      Scenario: work_item_start fires once across a deferred spawn
        Given a work item whose graph parks on its human start gate
        When the arming event defers the spawn and a later reply unparks it
        Then work_item_start ran exactly once, for the first event
        And session_spawn ran for the spawn that followed

    Requirement: docs/specs/issue-344/requirements.md R1.2 ("once per arming")
    """
    hooks = install()
    dispatcher, registry, tmux, store, announcer, _, link = _dispatcher(tmp_path)
    link.parked = True
    dispatcher.handle(comment("the-loop start", delivery="d-1"))
    assert _wait(lambda: link.armed == 1)
    assert tmux.spawns == []
    link.parked = False
    dispatcher.handle(comment("the-loop execute", delivery="d-2"))
    assert _wait(lambda: tmux.spawns)
    dispatcher.stop()
    assert len(points(hooks, "work_item_start")) == 1
    assert len(points(hooks, "session_spawn")) == 1


def test_a_start_refused_and_re_armed_asks_the_hooks_again(tmp_path, events, comments):
    hooks = install(
        work_item_start=lambda ctx: (
            {"proceed": False, "reason": "no"}
            if len(points(hooks, "work_item_start")) == 1
            else None
        )
    )
    dispatcher, registry, tmux, store, announcer, _, _ = _dispatcher(tmp_path)
    dispatcher.handle(comment("the-loop start", delivery="d-1"))
    assert _wait(lambda: events("hooks.refused"))
    dispatcher.handle(comment("the-loop start", delivery="d-2"))
    assert _wait(lambda: tmux.spawns)
    dispatcher.stop()
    assert len(points(hooks, "work_item_start")) == 2


# --------------------------------------------------------------- session_spawn


def test_a_hook_rewords_the_prompt_a_session_boots_on(tmp_path):
    """
    Feature: lifecycle hooks run where the thing they decide is about to happen
      Scenario: a hook rewords the prompt a session boots on
        Given a session_spawn hook that prefixes house rules to the prompt
        When the work item spawns
        Then the harness is launched on the hook's prompt
        And the hook saw the launch's facts: harness, cwd, endpoint, respawn=false

    Requirement: docs/specs/issue-344/requirements.md R2.7
    """
    hooks = install(
        session_spawn=lambda ctx: {"prompt": "HOUSE RULES FIRST\n\n" + ctx.prompt}
    )
    dispatcher, registry, tmux, store, announcer, _, _ = _dispatcher(tmp_path)
    dispatcher.handle(comment("the-loop start"))
    assert _wait(lambda: tmux.spawns)
    dispatcher.stop()
    (ref, prompt, cwd, resume) = tmux.spawns[0]
    assert ref == REF and prompt.startswith("HOUSE RULES FIRST\n\n")
    (spawn,) = points(hooks, "session_spawn")
    assert (spawn.endpoint.ref, spawn.harness, spawn.respawn) == (REF, "claude", False)
    assert spawn.cwd == cwd
    assert "GitHub webhook event" in spawn.prompt or spawn.prompt


def test_a_hook_can_prevent_a_launch(tmp_path, events, comments):
    hooks = install(
        session_spawn={"proceed": False, "reason": "no sessions during the freeze"}
    )
    dispatcher, registry, tmux, store, announcer, _, _ = _dispatcher(tmp_path)
    dispatcher.handle(comment("the-loop start"))
    assert _wait(lambda: events("hooks.refused"))
    dispatcher.stop()
    assert tmux.spawns == [] and registry.find_by_work_item(REF) is None
    assert store.get(REF) is not None, (
        "a refused launch does not disarm — a later event tries again"
    )
    assert any("freeze" in body for _, body in comments)
    (failed,) = events("session.spawn_failed")
    assert failed["will_retry"] is False and "freeze" in failed["error"]
    assert dispatcher.deduper.outcome("d-1") == "hook-refused"
    assert points(hooks, "session_spawned") == []


# ------------------------------------------------------------- session_spawned


def test_a_hook_silences_the_session_announcement(tmp_path):
    """
    Feature: lifecycle hooks run where the thing they decide is about to happen
      Scenario: a hook silences the session announcement
        Given a session_spawned hook that answers announce=false
        When the work item spawns
        Then the session is registered and the announcer is never called
        And with no such hook the announcer is called exactly as before

    Requirement: docs/specs/issue-344/requirements.md R2.7, R7.1
    """
    hooks = install(session_spawned={"announce": False})
    dispatcher, registry, tmux, store, announcer, _, _ = _dispatcher(tmp_path)
    dispatcher.handle(comment("the-loop start"))
    assert _wait(lambda: registry.find_by_work_item(REF) is not None)
    dispatcher.stop()
    assert announcer.announced == []
    (spawned,) = points(hooks, "session_spawned")
    assert spawned.tmux_target and spawned.harness_session_id
    registered = registry.find_by_work_item(REF)
    assert registered is not None
    assert spawned.harness_session_id == registered.harness_session_id

    lifecycle.reset()
    install()
    dispatcher2, registry2, tmux2, _, announcer2, _, _ = _dispatcher(
        tmp_path / "second"
    )
    dispatcher2.handle(comment("the-loop start"))
    assert _wait(lambda: announcer2.announced)
    dispatcher2.stop()
    assert announcer2.announced == [REF]


# ---------------------------------------------------------- work_item_complete


def test_a_closure_fires_work_item_complete(tmp_path, events):
    """
    Feature: lifecycle hooks run where the thing they decide is about to happen
      Scenario: a closure fires work_item_complete
        Given an armed work item with a session
        When its issue is closed
        Then work_item_complete carries state, kind, reason, source and actor
        And announce=false from the hook silences the channel closure announcement
        And the started mark is cleared with the control record

    Requirement: docs/specs/issue-344/requirements.md R1.2, R2.7, R7.1
    """
    hooks = install(work_item_complete={"announce": False})
    dispatcher, registry, tmux, store, announcer, posts, _ = _dispatcher(tmp_path)
    dispatcher.handle(comment("the-loop start"))
    assert _wait(lambda: registry.find_by_work_item(REF) is not None)
    dispatcher.handle(closed())
    assert _wait(lambda: store.ended(REF) is not None)
    dispatcher.stop()
    (complete,) = points(hooks, "work_item_complete")
    assert (complete.state, complete.kind, complete.reason) == (
        "closed",
        "issue",
        "issue-closed",
    )
    assert (complete.source, complete.actor) == ("webhook", "octocat")
    assert posts == [], "announce=false silenced work-item.closed"
    assert store.store.section(REF, "lifecycle") is None


def test_with_no_hooks_the_closure_is_announced_as_before(tmp_path):
    install()
    dispatcher, registry, tmux, store, announcer, posts, _ = _dispatcher(tmp_path)
    dispatcher.handle(comment("the-loop start"))
    assert _wait(lambda: registry.find_by_work_item(REF) is not None)
    dispatcher.handle(closed())
    assert _wait(lambda: store.ended(REF) is not None)
    dispatcher.stop()
    assert posts == [("work-item.closed", REF)]


# ------------------------------------------------------------- the graph runtime

GRAPH = {
    "name": "test-loop",
    "start": "select",
    "nodes": [
        {"id": "select", "phase": "phase-selection", "actor": "human"},
        {"id": "author", "phase": "requirements-definition"},
        {"id": "done", "phase": "complete", "terminal": True},
    ],
    "edges": [
        {"from": "select", "to": "author", "on": "pass"},
        {"from": "author", "to": "done", "on": "pass"},
    ],
}


class RecordingChannel:
    name = "recorder"

    def __init__(self):
        self.posted = []

    def subscribes(self, event_type):
        return event_type.startswith("phase.")

    def may_publish(self, event_type):
        return False

    def post(self, event):
        self.posted.append(event)
        return PostResult(channel=self.name, ok=True)


@pytest.fixture
def recorder(monkeypatch):
    channel = RecordingChannel()
    providers = dict(channels_base.CHANNEL_PROVIDERS)
    providers["recorder"] = lambda config, factory: channel
    monkeypatch.setattr(channels_base, "CHANNEL_PROVIDERS", providers)
    return channel


def _runtime(tmp_path):
    (tmp_path / "docs" / "specs" / "issue-15").mkdir(parents=True)
    return Runtime(
        tmp_path,
        graph=compile_graph(GRAPH),
        config={"channels": {"recorder": {"enabled": True}}},
    )


def test_a_phase_change_consults_the_hooks_before_the_channels_are_told(
    tmp_path, recorder
):
    """
    Feature: lifecycle hooks run where the thing they decide is about to happen
      Scenario: a phase change consults the hooks before the channels are told
        Given a phase_changed hook that answers notify=false for the first phase only
        When the graph starts, advances twice into a terminal node, and the terminal node is claimed
        Then phase_changed fired at the start (no from node), at the edge into another phase, and at the terminal node
        And the channels heard nothing for the start and everything after it
        And waiting_for_input(kind=gate) fired for the human start node

    Requirement: docs/specs/issue-344/requirements.md R1.2, R2.7, R7.1
    """
    hooks = install(
        phase_changed=lambda ctx: {"notify": False} if ctx.from_node == "" else None
    )
    rt = _runtime(tmp_path)
    rt.start("issue-15", ref=REF)
    assert recorder.posted == [], "notify=false silenced the first phase.started"
    rt.advance("issue-15", ref=REF)
    rt.advance("issue-15", ref=REF)
    rt.advance("issue-15", ref=REF)  # the claim on the terminal node

    changes = points(hooks, "phase_changed")
    assert [
        (c.from_node, c.to_node, c.from_phase, c.to_phase, c.terminal) for c in changes
    ] == [
        ("", "select", "", "phase-selection", False),
        ("select", "author", "phase-selection", "requirements-definition", False),
        ("author", "done", "requirements-definition", "complete", False),
        ("done", "done", "complete", "complete", True),
    ]
    assert changes[0].actor == "human" and changes[0].loop == "test-loop"
    assert changes[1].outcome == "pass"
    assert [e.event_type for e in recorder.posted] == [
        "phase.completed",
        "phase.started",
        "phase.completed",
        "phase.started",
        "phase.completed",
    ]
    (gate,) = points(hooks, "waiting_for_input")
    assert (gate.kind, gate.node, gate.loop) == ("gate", "select", "test-loop")
    assert gate.question == "" and gate.summary == ""


def test_with_no_hooks_the_runtime_publishes_as_before(tmp_path, recorder):
    install()
    rt = _runtime(tmp_path)
    rt.start("issue-15", ref=REF)
    rt.advance("issue-15", ref=REF)
    assert [e.event_type for e in recorder.posted] == [
        "phase.started",
        "phase.completed",
        "phase.started",
    ]


# ---------------------------------------------------------------------- ask


def test_an_agents_question_is_reworded_before_it_is_posted(
    tmp_path, monkeypatch, events
):
    """
    Feature: lifecycle hooks run where the thing they decide is about to happen
      Scenario: an agent's question is reworded before it is posted
        Given a waiting_for_input hook that tags questions and sets a summary
        When a session asks through `the-loop ask`
        Then the ticket comment carries the hook's text and the wait is recorded with it

    Requirement: docs/specs/issue-344/requirements.md R2.7
    """
    hooks = install(
        waiting_for_input=lambda ctx: {
            "question": "[policy] " + ctx.question,
            "summary": "tagged",
        }
    )
    posted = {}

    def fake_post(item, body, gh_binary="gh"):
        posted["ref"], posted["body"] = item.ref, body
        return True, "", "https://github.com/octo/repo/issues/15#issuecomment-3"

    monkeypatch.setattr(core_sessions, "post_issue_comment_with_url", fake_post)
    config = {"state": {"root": str(tmp_path / ".the-loop")}}
    result = core_sessions.ask_session(REF, "Which auth mode?", config)
    assert result["asked"] is True
    assert "[policy] Which auth mode?" in posted["body"]
    (asked,) = points(hooks, "waiting_for_input")
    assert (asked.kind, asked.work_item.ref) == ("question", REF)
    assert asked.actor
    (wait,) = events("session.awaiting_input")
    assert wait["question"] == "[policy] Which auth mode?"


# ------------------------------------------------------------ the work item's kind


def test_the_kind_is_read_off_the_payload_not_guessed():
    """PR #432 review: the entity carries what the point knows. A start names the item
    the payload is about — an issue, a pull request (even one GitHub delivers as an
    ``issue`` with a ``pull_request`` key) — and says nothing for a linked item."""
    from the_loop.sessions.registry import WorkItemRef
    from the_loop.webhook.dispatcher import _endpoint_item, _item_kind

    item = WorkItemRef.parse(REF)
    other = WorkItemRef.parse("github:octo/repo#99")

    class _Routed:
        def __init__(self, payload):
            self.payload = payload

    def _routed(payload) -> RoutedEvent:
        return cast(RoutedEvent, _Routed(payload))

    assert _item_kind(item, _routed({"issue": {"number": 15}})) == "issue"
    assert (
        _item_kind(
            item, _routed({"issue": {"number": 15, "pull_request": {"url": "x"}}})
        )
        == "pull-request"
    )
    assert _item_kind(item, _routed({"pull_request": {"number": 15}})) == "pull-request"
    assert _item_kind(item, _routed({"pull_request": {"number": 99}})) == ""
    assert _item_kind(item, _routed({})) == ""

    assert _endpoint_item(item, item).kind == ""
    pr = _endpoint_item(item, other)
    assert (pr.kind, pr.ref, pr.url) == (
        "pull-request",
        "github:octo/repo#99",
        "https://github.com/octo/repo/pull/99",
    )
