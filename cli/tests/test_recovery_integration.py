"""End-to-end: a daemon meeting a work item it has no record of (issue-363).

The reporter's devbox was destroyed and rebuilt. Within ninety seconds the new
daemon reset thirteen in-flight work items to their first node, replayed
sixty-four old comments — ten of them `the-loop execute` commands — and spawned
four items twice. Every one of those was a local record read as empty and empty
read as "this work item has never started".

These drive the real pieces, not doubles of them: a real ``GraphLink`` over the
shipped ``pdlc-work-item-loop``, a real ``Dispatcher``, a real ``Poller`` over
the real GitHub provider with canned ``gh`` output, and the real ``TmuxRunner``
liveness decision. Each scenario asserts the ABSENCE the reporter needed — no
advance out of the start node, no control command, no second spawn — because
that is what a test of the new happy path alone would not have caught.

Spec: docs/specs/issue-363/design.md; testing plan rows T5, T6, T7, T8, T12.
"""

from __future__ import annotations

import json
import subprocess
import time

import pytest
from conftest import FakeTmux, StubInteractiveAdapter
from test_poller_integration import GhState, _comment, wait_until

from the_loop import comments as comments_mod
from the_loop import eventlog
from the_loop.authz import mark_self_authored
from the_loop.control import ControlConfig
from the_loop.graph.state import GraphState
from the_loop.poller import GhClient, GitHubPollProvider, PollConfig, Poller, PollState
from the_loop.poller import parse_repos
from the_loop.runner import TmuxResult, TmuxRunner
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.state import StateLayout
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent
from the_loop.workitem import WorkItemStore

LABEL = "the-loop: auto-execute"
REF = WorkItemRef.parse("github:octo/repo#15")
ACTOR = "octocat"
SPEC = "issue-15"


# -- the world a rebuilt machine wakes up in ----------------------------------


def _checkout(root):
    """A fresh clone of the work item's repository — no branch, so no specs.

    This is the shape the report turned on: ``routing.workspace.strategy:
    clone`` prepares an ISSUE work item's checkout with no branch at all, so
    ``docs/specs/<id>/graph-state.json`` — which is checked in, on the work
    item's branch — is not in it.
    """
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "remote",
            "add",
            "origin",
            "https://github.com/octo/repo.git",
        ],
        check=True,
    )
    spec = root / "docs" / "specs" / SPEC
    spec.mkdir(parents=True)
    (spec / "execution-log.md").write_text("# Execution Log\n")
    return root


class _FakeGitHub:
    """The graph's github integration, reaching no network."""

    def __init__(self):
        self.posted: list[str] = []
        self.labels: list[str] = []

    def call(self, op, **params):
        if op == "list-comments":
            return {"comments": [{"body": body} for body in self.posted]}
        if op == "add-comment":
            self.posted.append(str(params.get("body") or ""))
        if op == "set-labels":
            self.labels.extend(str(label) for label in (params.get("labels") or []))
        return {}


@pytest.fixture()
def github(monkeypatch):
    provider = _FakeGitHub()
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve", lambda target, config: provider
    )
    return provider


@pytest.fixture()
def checkout(tmp_path):
    return _checkout(tmp_path / "checkout")


@pytest.fixture()
def events(tmp_path):
    """The daemon's own event log, so a scenario can assert what did NOT fire."""
    path = tmp_path / "events.jsonl"
    eventlog.configure("gh-webhook", path=path)
    try:
        yield lambda: [record["event"] for record in eventlog.read_events(path)]
    finally:
        eventlog.reset()


def _dispatcher(tmp_path, **routing):
    return Dispatcher(
        registry=SessionRegistry(tmp_path / "sessions"),
        adapters={},
        config=RoutingConfig.from_mapping(
            {"authorizedUsers": [ACTOR], "control": {"enabled": False}, **routing},
            StateLayout(root=str(tmp_path / "state")),
        ),
    )


def _labelled(*labels, event="issues", action="labeled"):
    return RoutedEvent(
        event=event,
        action=action,
        delivery_id="d-1",
        work_items=[REF],
        payload={"issue": {"number": 15, "labels": [{"name": n} for n in labels]}},
    )


def _state(checkout):
    return GraphState.load(checkout / "docs" / "specs" / SPEC, SPEC)


# -- R1: a machine that has forgotten a work item never rewinds it ------------


def test_a_forgotten_item_is_not_rewound_and_still_gets_a_session(
    tmp_path, checkout, github, events
):
    """
    Feature: Surviving a machine loss
    Scenario: A rebuilt daemon meets a work item that is already at implementation
      Given a work item labelled `loop:implementation` and a checkout with no graph state
      When the daemon enters the graph for it
      Then no node is entered, no phase label is written and no gate is re-asked
      And the spawn is not held back, so the item still gets a session

    Requirement: docs/specs/issue-363/bugfix.md#R1.1
    """
    dispatcher = _dispatcher(tmp_path)

    waits = dispatcher.graphlink.on_arm(
        REF, str(checkout), routed=_labelled(LABEL, "loop:implementation")
    )
    dispatcher.graphlink.on_spawn(
        REF,
        str(checkout),
        session_id="s-1",
        routed=_labelled(LABEL, "loop:implementation"),
    )

    assert _state(checkout).current_node == "", "the pointer must not be placed"
    assert not GraphState.path_for(checkout / "docs" / "specs" / SPEC).is_file()
    assert github.labels == [], "no early label written over a late one"
    assert github.posted == [], "no gate re-asked"
    assert waits is False, "R1.2: the spawn still happens"
    assert "graph.rewind_refused" in events()
    assert "graph.started" not in events()


def test_an_event_on_a_forgotten_item_does_not_advance_it_either(
    tmp_path, checkout, github, events
):
    """
    Feature: Surviving a machine loss
    Scenario: An old `the-loop execute` reaches the graph of a forgotten item
      Given a work item labelled `loop:design` and no local graph state
      When a comment event is handed to the graph
      Then nothing is evaluated, because `advance` on an empty state reads the
           start node and would freeze a selection from a days-old comment

    Requirement: docs/specs/issue-363/bugfix.md#R1.1
    """
    dispatcher = _dispatcher(tmp_path)
    routed = RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id="d-2",
        work_items=[REF],
        payload={
            "issue": {"number": 15, "labels": [{"name": "loop:design"}]},
            "comment": {"body": "the-loop execute", "user": {"login": ACTOR}},
        },
    )

    assert dispatcher.graphlink.on_event(REF, str(checkout), routed) is None
    assert _state(checkout).current_node == ""
    assert github.posted == [] and github.labels == []
    assert "graph.frozen" not in events()


def test_an_item_with_no_phase_label_still_enters_the_graph(tmp_path, checkout, github):
    """
    Feature: Surviving a machine loss
    Scenario: Every work item the-loop has never touched is unaffected
      Given a labelled-for-autoexecute work item with no `loop:` phase label
      When the daemon enters the graph for it
      Then it enters the start node exactly as it always has

    Requirement: docs/specs/issue-363/bugfix.md#R1.3
    """
    dispatcher = _dispatcher(tmp_path)

    dispatcher.graphlink.on_spawn(REF, str(checkout), routed=_labelled(LABEL))

    assert _state(checkout).current_node == "phase-selection"
    assert github.labels == ["loop:phase-selection"]


def test_a_started_item_is_judged_by_its_state_file_not_its_label(
    tmp_path, checkout, github
):
    """
    Feature: Surviving a machine loss
    Scenario: A machine that HAS the pointer is never second-guessed
      Given a work item this machine is already walking
      When a later event arrives carrying a phase label
      Then the graph runs normally — the file check comes first

    Requirement: docs/specs/issue-363/design.md#_may_start
    """
    dispatcher = _dispatcher(tmp_path)
    dispatcher.graphlink.on_spawn(REF, str(checkout), routed=_labelled(LABEL))
    assert _state(checkout).current_node == "phase-selection"

    dispatcher.graphlink.on_event(
        REF, str(checkout), _labelled(LABEL, "loop:phase-selection")
    )

    assert _state(checkout).current_node == "phase-selection"


def test_a_corrupt_state_file_refuses_rather_than_rewinding(
    tmp_path, checkout, github, events
):
    """
    Feature: Surviving a machine loss
    Scenario: A `graph-state.json` that will not parse is not a pointer
      Given a work item labelled `loop:design` whose state file is unreadable
      When the daemon enters the graph for it
      Then it refuses, because the file is KEPT for post-mortem (issue-109 R8.3)
           and `GraphState.load` reads it as a fresh state — which `start` would
           walk from the start node exactly as it walks a missing one
      And the corrupt file is left on disk untouched

    Requirement: docs/specs/issue-363/bugfix.md#R1.1
    """
    dispatcher = _dispatcher(tmp_path)
    path = GraphState.path_for(checkout / "docs" / "specs" / SPEC)
    path.write_text("{ this is not json")

    dispatcher.graphlink.on_spawn(
        REF, str(checkout), routed=_labelled(LABEL, "loop:design")
    )

    assert path.read_text() == "{ this is not json"
    assert github.labels == [] and github.posted == []
    assert "graph.rewind_refused" in events()


def test_abuse_a_forged_complete_label_never_places_a_pointer(
    tmp_path, checkout, github, events
):
    """
    Feature: Surviving a machine loss
    Scenario: Anyone who can label a ticket cannot move it through the graph
      Given a brand-new work item somebody has labelled `loop:complete`
      When the daemon enters the graph for it
      Then the answer is a refusal and a notice — never a pointer at `complete`

    Requirement: docs/specs/issue-363/bugfix.md#Security considerations
    """
    dispatcher = _dispatcher(tmp_path)

    dispatcher.graphlink.on_spawn(
        REF, str(checkout), routed=_labelled(LABEL, "loop:complete")
    )

    assert _state(checkout).current_node == ""
    assert github.labels == [] and github.posted == []
    assert "graph.rewind_refused" in events()


# -- R2: the graph position travels with the work item ------------------------


def test_a_published_position_is_restored_byte_for_byte(
    tmp_path, checkout, github, events
):
    """
    Feature: Surviving a machine loss
    Scenario: The pointer published by the old machine is adopted by the new one
      Given a portable record carrying the work item's graph state
      And a checkout with no graph state of its own
      When the daemon enters the graph for it
      Then the state file is restored verbatim and the item keeps its node

    Requirement: docs/specs/issue-363/bugfix.md#R2.2
    """
    dispatcher = _dispatcher(tmp_path)
    # The old machine's state file, exactly as it would have been written there.
    old_machine = GraphState(work_item=SPEC, loop="pdlc-work-item-loop")
    old_machine.enter("implementation")
    published = old_machine.as_dict()
    dispatcher.control_store.record_graph_position(
        REF, {"at": "2026-09-13T00:00:00Z", "state": published}
    )

    dispatcher.graphlink.on_spawn(
        REF,
        str(checkout),
        session_id="s-1",
        routed=_labelled(LABEL, "loop:implementation"),
    )

    path = GraphState.path_for(checkout / "docs" / "specs" / SPEC)
    restored = json.loads(path.read_text())
    assert restored["currentNode"] == "implementation"
    assert restored["nodes"] == published["nodes"]
    assert "graph.position_restored" in events()
    assert "graph.rewind_refused" not in events()


def test_the_position_is_published_on_every_graph_write(tmp_path, checkout, github):
    """
    Feature: Surviving a machine loss
    Scenario: What the next machine will restore is written as the graph moves
      Given a work item entering its graph
      When the start node is entered
      Then its whole graph state is on the portable record, beside the selection

    Requirement: docs/specs/issue-363/bugfix.md#R2.1
    """
    dispatcher = _dispatcher(tmp_path)

    dispatcher.graphlink.on_spawn(REF, str(checkout), routed=_labelled(LABEL))

    published = dispatcher.control_store.graph_position(REF)
    assert published is not None and published["at"]
    on_disk = json.loads(
        GraphState.path_for(checkout / "docs" / "specs" / SPEC).read_text()
    )
    assert published["state"] == on_disk, (
        "a restore must be a move, not a re-derivation"
    )


def test_abuse_a_portable_position_never_overwrites_local_state(
    tmp_path, checkout, github
):
    """
    Feature: Surviving a machine loss
    Scenario: A tracked record cannot move a pointer this machine established
      Given a work item already standing on its start node here
      And a portable record proposing a position at `complete`
      When a later event reaches the graph
      Then the local state file is untouched

    Requirement: docs/specs/issue-363/bugfix.md#Security considerations
    """
    dispatcher = _dispatcher(tmp_path)
    dispatcher.graphlink.on_spawn(REF, str(checkout), routed=_labelled(LABEL))
    dispatcher.control_store.record_graph_position(
        REF, {"at": "t", "state": {"workItem": SPEC, "currentNode": "complete"}}
    )

    dispatcher.graphlink.on_event(REF, str(checkout), _labelled(LABEL))

    assert _state(checkout).current_node == "phase-selection"


# -- R3: a control command is executed once, ever -----------------------------


def _poller(tmp_path, gh, comment_runner=None, registry=None):
    registry = registry or SessionRegistry(tmp_path / "sessions")
    tmux = FakeTmux()
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=RoutingConfig(
            spawn_on_unmatched="labeled",
            control=ControlConfig(require_start_command=False),
            authorized_users=[ACTOR],
            portable_dir=str(tmp_path / "portable"),
        ),
        tmux_runner=tmux,
    )
    provider = GitHubPollProvider(
        parse_repos(["octo/repo"]), LABEL, gh=GhClient(runner=gh.runner)
    )
    poller = Poller(
        providers=[provider],
        registry=registry,
        dispatcher=dispatcher,
        config=PollConfig(),
        state=PollState(WorkItemStore(tmp_path / "portable")),
        authorized_users=[ACTOR],
        **({"comment_runner": comment_runner} if comment_runner else {}),
    )
    return registry, tmux, dispatcher, poller


class _Posts:
    """Captures the `gh api … /comments` call without running it."""

    def __init__(self):
        self.bodies = []

    def __call__(self, cmd, **kwargs):
        if "-f" in cmd:
            self.bodies.append(cmd[cmd.index("-f") + 1].removeprefix("body="))
        return subprocess.CompletedProcess(cmd, 0, "{}", "")


@pytest.fixture()
def gh_on_path(monkeypatch):
    """`post_issue_comment` refuses without a `gh` binary; there is none here."""
    monkeypatch.setattr(comments_mod.shutil, "which", lambda _: "/usr/bin/gh")


def test_a_forgotten_items_old_commands_are_baselined_and_announced_once(
    tmp_path, events, gh_on_path
):
    """
    Feature: Surviving a machine loss
    Scenario: A rebuilt poller does not re-run a week of commands
      Given a labelled work item whose thread carries the-loop's own posts
      And an old authorized `the-loop execute` and an old approval on it
      When a daemon that has never seen the item polls
      Then the whole thread is baselined, no command is forwarded
      And exactly one notice is posted, naming the cutoff

    Requirement: docs/specs/issue-363/bugfix.md#R3.1
    """
    gh = GhState()
    gh.issues[0]["labels"].append({"name": "loop:implementation"})
    gh.comments = [
        _comment("IC_1", mark_self_authored("🤖 phase selection recorded")),
        _comment("IC_2", "the-loop execute", author=ACTOR),
        _comment("IC_3", "approved", author=ACTOR),
    ]
    posts = _Posts()
    registry, tmux, dispatcher, poller = _poller(tmp_path, gh, comment_runner=posts)

    poller.poll_once()
    assert wait_until(lambda: len(tmux.spawns) == 1)
    poller.poll_once()
    time.sleep(0.05)
    dispatcher.stop()

    assert tmux.delivers == [], "no old comment is forwarded"
    assert "control.command" not in events()
    assert "poll.context_lost" in events()
    assert len(posts.bodies) == 1, "one notice, once"
    assert "no longer has its own record" in posts.bodies[0]
    assert len(tmux.spawns) == 1, "the item still gets its session, and only one"


def test_a_new_items_pending_start_command_is_still_forwarded(
    tmp_path, events, gh_on_path
):
    """
    Feature: Surviving a machine loss
    Scenario: issue-119 is intact for a work item nobody has worked
      Given a labelled work item with no `loop:` phase label and no the-loop posts
      And an authorized `the-loop execute` posted before the poller first saw it
      When the poller runs
      Then that comment is NOT baselined away — it is acted on, as before
      And nothing is announced, because nothing was forgotten

    Requirement: docs/specs/issue-363/bugfix.md#R3.2
    """
    gh = GhState()
    gh.comments = [_comment("IC_1", "the-loop execute", author=ACTOR)]
    posts = _Posts()
    registry, tmux, dispatcher, poller = _poller(tmp_path, gh, comment_runner=posts)

    poller.poll_once()
    assert wait_until(lambda: "control.command" in events())
    dispatcher.stop()

    assert "poll.context_lost" not in events()
    assert posts.bodies == [], "nothing to announce about an untouched item"


def test_abuse_an_unauthorized_command_is_still_never_executed(tmp_path, events):
    """
    Feature: Surviving a machine loss
    Scenario: The age rule only ever withholds
      Given a forgotten work item whose thread carries a stranger's `the-loop execute`
      When the poller baselines the thread
      Then the command is not executed — as it never was, for its own reason

    Requirement: docs/specs/issue-363/bugfix.md#Security considerations
    """
    gh = GhState()
    gh.issues[0]["labels"].append({"name": "loop:verification"})
    gh.comments = [_comment("IC_1", "the-loop stop", author="a-stranger")]
    registry, tmux, dispatcher, poller = _poller(tmp_path, gh, comment_runner=_Posts())

    poller.poll_once()
    time.sleep(0.05)
    dispatcher.stop()

    assert "control.command" not in events()
    assert tmux.delivers == []


# -- R4: a session that is still booting is not a session that has died -------


class _BootingTmux(FakeTmux):
    """A FakeTmux whose pane does not answer — with the REAL deliver decision.

    ``FakeTmux`` overrides ``deliver`` wholesale, which is what the dispatcher
    tests want; here the decision under test *is* ``TmuxRunner.deliver``, so it
    is called for real over a pane that reports nothing and a ``deliver_to``
    that records instead of pasting.
    """

    def has_live_session(self, target) -> bool:
        return False

    def deliver(self, session, prompt, timeout=None):
        return TmuxRunner.deliver(self, session, prompt, timeout)

    def deliver_to(self, target, prompt, timeout=None):
        self.delivers.append((target, prompt))
        return TmuxResult(ok=True)


def test_a_comment_arriving_during_the_boot_does_not_spawn_a_second_session(
    tmp_path, events
):
    """
    Feature: Surviving a machine loss
    Scenario: A comment queued a moment before the spawn does not race it
      Given a session registered seconds ago whose pane is not answering yet
      When an event is delivered into it
      Then the delivery is released for retry, not treated as a dead session
      And nothing is respawned and no second session is spawned

    Requirement: docs/specs/issue-363/bugfix.md#R4.1
    """
    registry = SessionRegistry(tmp_path / "sessions")
    tmux = _BootingTmux()
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=RoutingConfig(
            authorized_users=[ACTOR],
            portable_dir=str(tmp_path / "portable"),
        ),
        tmux_runner=tmux,
    )
    registry.register(
        Session(
            work_item=REF,
            harness="claude",
            harness_session_id="just-minted",
            cwd=str(tmp_path),
            tmux_target="loop-github-octo-repo-15",
        )
    )

    dispatcher.handle(
        RoutedEvent(
            event="issue_comment",
            action="created",
            delivery_id="d-9",
            work_items=[REF],
            payload={"comment": {"body": "hi", "user": {"login": ACTOR}}},
        )
    )
    time.sleep(0.05)
    dispatcher.stop()

    kinds = events()
    assert "session.respawned" not in kinds
    assert "session.resume_failed" not in kinds
    assert "session.spawned" not in kinds
    assert tmux.spawns == [] and tmux.delivers == []
