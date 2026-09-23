"""An operator's own graph, armed from a comment, end to end (issue-343).

    cli-config.yaml declares routing.graph.graphs (a file, and the words that arm it)
        → the dispatcher parses `the-loop triage` as `start` onto that loop
        → the control record keeps the loop
        → the spawn enters the graph through the real GraphLink and Runtime
        → work-item-state.json records the operator's loop by name

A real :class:`Dispatcher` over a real ``git`` checkout (the link refuses to drive a
graph in a checkout that is not the work item's own), with the harness side faked
at the tmux seam and GitHub faked at the integrations seam. No network.

Feature: an operator brings their own graph and binds commands to it
Requirement: docs/specs/issue-343/requirements.md
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from conftest import FakeTmux, StubInteractiveAdapter
from the_loop.control import ControlStore
from the_loop.graph import extensions
from the_loop.graph.state import WorkItemState
from the_loop.sessions import SessionRegistry
from the_loop.state import StateLayout
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent, extract_work_items

NAME = "acme-triage-loop"
QUICK = "acme-quick-loop"
LABEL = "the-loop: auto-execute"
REF = "github:octo/repo#343"
ITEM = "issue-343"
OWNER = "octocat"

TRIAGE = """
version: 1
start: triage
nodes:
  - id: triage
    phase: implementation
    actor: agent
    command: acme:triage
    entry: [set-phase-label]
    exit: []
  - id: complete
    phase: complete
    actor: agent
    terminal: true
    entry: [set-phase-label]
  - id: cleanup
    phase: cleanup
    actor: code
    terminal: true
    entry: [set-phase-label]
edges:
  - {from: triage, to: complete, on: pass}
"""


class _FakeGitHub:
    def __init__(self):
        self.labels: list[str] = []

    def call(self, op, **params):
        if op == "set-labels":
            self.labels.extend(str(label) for label in (params.get("labels") or []))
        if op == "list-comments":
            return {"comments": []}
        return {}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    extensions.clear_module_cache()
    provider = _FakeGitHub()
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve", lambda target, config: provider
    )
    yield provider
    extensions.clear_module_cache()


def _checkout(root: Path) -> Path:
    root.mkdir(parents=True)
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
    (root / "docs" / "specs" / ITEM).mkdir(parents=True)
    return root


def _setup(tmp_path: Path, monkeypatch):
    """The operator's config on disk (read by the runtime builder) and the same
    routing block handed to the dispatcher, as the daemon does."""
    (tmp_path / "graphs").mkdir()
    (tmp_path / "graphs" / "triage.yaml").write_text(TRIAGE.lstrip())
    (tmp_path / "graphs" / "quick.yaml").write_text(TRIAGE.lstrip())
    graph_block = {
        "graphs": [
            {"name": NAME, "path": "graphs/triage.yaml", "commands": ["triage"]},
            {"name": QUICK, "path": "graphs/quick.yaml", "commands": ["do"]},
        ]
    }
    config_path = tmp_path / "cli-config.yaml"
    config_path.write_text(
        'version: "0.10.0"\n'
        "routing:\n"
        "  graph:\n"
        "    graphs:\n"
        f"      - {{name: {NAME}, path: graphs/triage.yaml, commands: [triage]}}\n"
        f"      - {{name: {QUICK}, path: graphs/quick.yaml, commands: [do]}}\n"
    )
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(config_path))
    checkout = _checkout(tmp_path / "checkout")
    tmux = FakeTmux()
    dispatcher = Dispatcher(
        registry=SessionRegistry(tmp_path / "state" / "local"),
        adapters={"claude": StubInteractiveAdapter()},
        config=RoutingConfig.from_mapping(
            {
                "registryDir": str(tmp_path / "state" / "local"),
                "spawnOnUnmatched": "labeled",
                "autoExecuteLabels": [LABEL],
                "spawnWorkdir": str(checkout),
                "authorizedUsers": [OWNER],
                "graph": graph_block,
            },
            StateLayout(root=str(tmp_path / "state")),
        ),
        tmux_runner=tmux,
    )
    store = ControlStore(str(tmp_path / "state" / "portable"))
    return dispatcher, tmux, store, checkout


def _comment(body: str, author: str = OWNER, delivery: str = "d-1") -> RoutedEvent:
    payload = {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 343, "labels": [{"name": LABEL}]},
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
        labeled=False,
    )


def _wait(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _state(checkout: Path) -> WorkItemState:
    return WorkItemState.load(checkout / "docs" / "specs" / ITEM, ITEM)


def test_a_new_command_arms_a_work_item_onto_the_operators_graph(tmp_path, monkeypatch):
    """
    Feature: an operator brings their own graph and binds commands to it
      Scenario: a new command arms a work item onto the operator's graph
        Given a CLI config declaring acme-triage-loop, armed by the new word `triage`
        And a labelled work item in a checkout of its own repository
        When an authorized user comments `the-loop triage`
        Then the control record says `start` and names acme-triage-loop
        And a session is spawned for the work item
        And the work item's graph state walks acme-triage-loop from its start node

    Requirement: docs/specs/issue-343/requirements.md R3.4, R3.5, R4.1
    """
    dispatcher, tmux, store, checkout = _setup(tmp_path, monkeypatch)
    try:
        dispatcher.handle(_comment("the-loop triage"))
        assert _wait(lambda: len(tmux.spawns) == 1)
        record = store.get(REF)
        assert record is not None
        assert (record.command, record.loop) == ("start", NAME)
        assert _wait(lambda: _state(checkout).loop == NAME)
        assert _state(checkout).current_node == "triage"
    finally:
        dispatcher.stop(timeout=5)


def test_an_overridden_arming_command_selects_the_operators_graph(
    tmp_path, monkeypatch
):
    """
    Feature: an operator brings their own graph and binds commands to it
      Scenario: an overridden arming command selects the operator's graph
        Given a CLI config binding the shipped `do` command to acme-quick-loop
        When an authorized user comments `the-loop do`
        Then the control record says `do` and names acme-quick-loop
        And the work item walks acme-quick-loop, not pdlc-adhoc-loop

    Requirement: docs/specs/issue-343/requirements.md R3.6, R4.1
    """
    dispatcher, tmux, store, checkout = _setup(tmp_path, monkeypatch)
    try:
        dispatcher.handle(_comment("the-loop do"))
        assert _wait(lambda: len(tmux.spawns) == 1)
        record = store.get(REF)
        assert record is not None
        assert (record.command, record.loop) == ("do", QUICK)
        assert _wait(lambda: _state(checkout).loop == QUICK)
    finally:
        dispatcher.stop(timeout=5)


def test_unauthorized_custom_command_is_refused(tmp_path, monkeypatch):
    """
    Feature: an operator brings their own graph and binds commands to it
      Scenario: an unauthorized user's new command is refused
        Given a CLI config declaring the new word `triage`
        When a user outside authorizedUsers comments `the-loop triage`
        Then nothing is recorded, nothing is spawned, and no graph is entered

    Requirement: docs/specs/issue-343/requirements.md, Security considerations abuse case 3
    """
    dispatcher, tmux, store, checkout = _setup(tmp_path, monkeypatch)
    try:
        dispatcher.handle(_comment("the-loop triage", author="stranger"))
        time.sleep(0.2)
        assert tmux.spawns == []
        assert store.get(REF) is None
        assert _state(checkout).loop == ""
    finally:
        dispatcher.stop(timeout=5)
