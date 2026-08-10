"""End-to-end: the-loop adopting a repository that never ran its setup (issue-193).

These drive the **real** call sites — ``GraphLink`` on the ingress path (the poller and
the webhook share it) and ``core.graphs`` on the CLI path — against real ``git init``
checkouts, because the property under test is exactly the one a unit test of
``harness_config.scaffold`` cannot show: that adoption happens where the-loop starts
working a repository, behind the gates that decide whether it may touch that checkout at
all, and never where it must not.

Feature: a default harness config for repositories that never adopted the-loop
Requirement: docs/specs/issue-193/requirements.md
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from the_loop import eventlog, harness_config
from the_loop.control import CONTRIBUTE, ControlConfig, ControlStore
from the_loop.core import graphs as core_graphs
from the_loop.graphlink import GraphLink, GraphLinkConfig
from the_loop.sessions import WorkItemRef

REF = WorkItemRef.parse("github:octo/repo#193")
WORK_ITEM = "issue-193"


def _checkout(root: Path, origin: str = "https://github.com/octo/repo.git") -> Path:
    """A git checkout with an origin and **no** `.the-loop/` — an unadopted repository."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "remote", "add", "origin", origin], check=True
    )
    return root


def _link(**kwargs) -> GraphLink:
    """A link with the start gate off — this suite is about adoption, not arming."""
    kwargs.setdefault("control", ControlConfig(require_start_command=False))
    return GraphLink(GraphLinkConfig(), **kwargs)


def _adopted(root: Path) -> Path:
    return root / ".the-loop" / "harness-config.yaml"


@pytest.fixture()
def events(tmp_path):
    """The real event log, so `harness.config_scaffolded` is asserted as emitted."""
    log = eventlog.configure(
        "test-harness-config-scaffold", path=tmp_path / "events.jsonl", enabled=True
    )
    yield log
    eventlog.reset()


# ------------------------------------------------------------------ the ingress path


def test_the_ingress_adopts_a_repository_that_never_ran_the_setup(tmp_path, events):
    """
    Feature: a default harness config for repositories that never adopted the-loop
    Scenario: the poller or webhook drives a work item in an unadopted repository
      Given a checkout of the work item's own repository with no `.the-loop/` at all
      When the ingress→graph coupling handles a spawn for that work item
      Then `.the-loop/harness-config.yaml` holds the-loop's built-in defaults
      And the file names the work item's repository, so `originRepo` resolves
      And the event log records that the-loop — not a person — wrote it

    Requirement: docs/specs/issue-193/requirements.md R2.1, R2.2, R2.3
    """
    root = _checkout(tmp_path / "repo")
    _link().on_spawn(REF, str(root))

    assert _adopted(root).is_file()
    loaded = harness_config.load(root)
    assert harness_config.spec_dir(loaded) == harness_config.DEFAULT_SPEC_DIR
    assert harness_config.origin_repo(loaded) == "octo/repo"
    written = [
        record
        for record in eventlog.read_events(events.path)
        if record["event"] == "harness.config_scaffolded"
    ]
    assert len(written) == 1
    assert written[0]["repo"] == "octo/repo"


def test_a_repository_is_adopted_even_when_its_graph_is_skipped(tmp_path, events):
    """
    Feature: a default harness config for repositories that never adopted the-loop
    Scenario: the work item has no spec directory yet
      Given an unadopted checkout in which the work item has no spec directory
      When the ingress→graph coupling handles a spawn
      Then the graph is still skipped, exactly as before this change
      And the repository is adopted anyway, because the session the daemon just
           spawned is already running there and needs a config to read

    Requirement: docs/specs/issue-193/requirements.md R2.1
    """
    root = _checkout(tmp_path / "repo")
    _link().on_spawn(REF, str(root))

    assert _adopted(root).is_file()
    assert not (root / "docs" / "specs" / WORK_ITEM / "graph-state.json").exists()
    skips = [
        record
        for record in eventlog.read_events(events.path)
        if record["event"] == "graph.skipped"
    ]
    assert [record["reason"] for record in skips] == ["no-spec-dir"]


def test_a_foreign_checkout_is_never_adopted(tmp_path, events):
    """
    Feature: a default harness config for repositories that never adopted the-loop
    Scenario: the checkout is not the work item's own repository
      Given a checkout whose origin is a different repository
      When the ingress→graph coupling handles a spawn for the work item
      Then nothing is written into it — adoption stays behind the ownership proof

    Requirement: docs/specs/issue-193/requirements.md abuse case 2
    """
    root = _checkout(tmp_path / "repo", origin="https://github.com/someone/else.git")
    _link().on_spawn(REF, str(root))

    assert not (root / ".the-loop").exists()


def test_a_contribution_never_adopts_its_host_repository(tmp_path, events):
    """
    Feature: a default harness config for repositories that never adopted the-loop
    Scenario: the-loop was invited into somebody else's work item as a contributor
      Given an unadopted checkout and a control record arming `the-loop contribute`
      When the ingress→graph coupling handles a spawn for that work item
      Then no harness config is written — a guest does not install itself
      And issue-185's rules keep applying to that repository unchanged

    Requirement: docs/specs/issue-193/requirements.md R4.1
    """
    root = _checkout(tmp_path / "repo")
    control = ControlStore(tmp_path / "state")
    control.record(REF, CONTRIBUTE, actor="owner")

    _link(control_store=control).on_spawn(REF, str(root))

    assert not (root / ".the-loop").exists()


def test_an_adopted_repository_is_left_alone_on_every_later_event(tmp_path, events):
    """
    Feature: a default harness config for repositories that never adopted the-loop
    Scenario: the repository already carries a configuration
      Given a checkout whose harness config an operator wrote
      When the ingress→graph coupling handles events for it
      Then that file is byte-for-byte what the operator wrote

    Requirement: docs/specs/issue-193/requirements.md R2.4, abuse case 3
    """
    root = _checkout(tmp_path / "repo")
    (root / ".the-loop").mkdir()
    mine = "workflow:\n  specDir: my/specs\n  phaseLabelPrefix: 'stage:'\n"
    _adopted(root).write_text(mine, encoding="utf-8")

    _link().on_spawn(REF, str(root))
    _link().on_spawn(REF, str(root))

    assert _adopted(root).read_text(encoding="utf-8") == mine
    assert not [
        record
        for record in eventlog.read_events(events.path)
        if record["event"] == "harness.config_scaffolded"
    ]


def test_the_repository_is_adopted_before_the_harness_is_started(tmp_path):
    """
    Feature: a default harness config for repositories that never adopted the-loop
    Scenario: the daemon spawns a session into a fresh, unconfigured clone
      Given an unadopted checkout of the work item's own repository
      When the dispatcher spawns a session for that work item
      Then `.the-loop/harness-config.yaml` already exists **at the moment
           `tmux.spawn` is called**, so the harness cannot start in a checkout
           that has no configuration to read

    The assertion is deliberately made from *inside* the spawn call rather than
    after the dispatch returns: the outcome was already right before issue-201,
    and the ordering was not.

    Requirement: docs/specs/issue-201/bugfix.md R1
    """
    from the_loop.control import ControlConfig
    from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
    from the_loop.webhook.router import RoutedEvent
    from the_loop.sessions import SessionRegistry
    from conftest import FakeTmux, StubInteractiveAdapter

    root = _checkout(tmp_path / "repo")

    class SpawnObserver(FakeTmux):
        """Records whether the config existed when the harness was started."""

        config_present_at_spawn = None

        def spawn(self, *args, **kwargs):
            SpawnObserver.config_present_at_spawn = _adopted(root).is_file()
            return super().spawn(*args, **kwargs)

    tmux = SpawnObserver()
    dispatcher = Dispatcher(
        registry=SessionRegistry(tmp_path / "sessions"),
        adapters={"claude": StubInteractiveAdapter()},
        config=RoutingConfig(
            spawn_on_unmatched="always",
            spawn_workdir=str(root),
            control=ControlConfig(require_start_command=False),
        ),
        tmux_runner=tmux,
    )
    payload = {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 193},
        "comment": {"body": "please fix", "user": {"login": "octocat"}},
    }
    try:
        dispatcher.handle(
            RoutedEvent(
                event="issue_comment",
                action="created",
                delivery_id="d-201",
                work_items=[REF],
                payload=payload,
            )
        )
        deadline = time.monotonic() + 5
        while not tmux.spawns and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        dispatcher.stop()

    assert tmux.spawns, "the dispatcher must have spawned a session"
    assert SpawnObserver.config_present_at_spawn is True, (
        "the harness was started in a checkout with no harness config — adoption "
        "must precede tmux.spawn, not follow it (issue-201)"
    )


def test_resolving_a_prompts_graph_context_adopts_nothing(tmp_path, events):
    """
    Feature: a default harness config for repositories that never adopted the-loop
    Scenario: the dispatcher resolves a work item's graph context before delivering
      Given an unadopted checkout of the work item's own repository
      When the coupling is asked for the item's context — a read that happens before
           every delivery and is documented as mutating nothing
      Then nothing is written, because "only a config file" is how that stops being true

    Requirement: docs/specs/issue-193/requirements.md R2.1 (adoption is bounded to the
    actions that drive the graph)
    """
    root = _checkout(tmp_path / "repo")
    _link().context(REF, str(root))

    assert not (root / ".the-loop").exists()


def test_releasing_a_work_items_resources_adopts_nothing(tmp_path, events):
    """
    Feature: a default harness config for repositories that never adopted the-loop
    Scenario: the-loop is releasing the work item's local resources
      Given an unadopted checkout whose work item is being cleaned up
      When the cleanup transition is recorded
      Then no config is written into a checkout that is about to be removed

    Requirement: docs/specs/issue-193/requirements.md R2.1
    """
    root = _checkout(tmp_path / "repo")
    _link().on_cleanup(REF, str(root), reason="done")

    assert not (root / ".the-loop").exists()


# ---------------------------------------------------------------------- the CLI path


def test_a_mutating_graph_verb_adopts_the_repository(tmp_path):
    """
    Feature: a default harness config for repositories that never adopted the-loop
    Scenario: a session runs a state-changing graph verb in an unadopted checkout
      Given an unadopted repository
      When `the-loop graph complete` runs against it
      Then the repository is adopted before the runtime is built, so the verb and
           the daemon read one configuration rather than two defaults

    Requirement: docs/specs/issue-193/requirements.md R3.1
    """
    root = _checkout(tmp_path / "repo")
    core_graphs.complete(str(root), WORK_ITEM)
    assert _adopted(root).is_file()


def test_a_read_only_command_writes_nothing(tmp_path):
    """
    Feature: a default harness config for repositories that never adopted the-loop
    Scenario: asking a question must not change the answer
      Given an unadopted repository
      When `the-loop check` and `the-loop graph show` run against it
      Then nothing is written — the check operation is pure by contract (R8.8)

    Requirement: docs/specs/issue-193/requirements.md R3.2
    """
    root = _checkout(tmp_path / "repo")
    core_graphs.check(str(root), WORK_ITEM)
    core_graphs.show(str(root))
    assert not (root / ".the-loop").exists()
