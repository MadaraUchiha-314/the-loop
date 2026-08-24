"""The `cleanup` node and how the-loop enters it (issue-186, R5).

Three things are pinned here. The **shape**: the two work-item-level loops
declare a terminal `cleanup` node and `pdlc-pr-loop` deliberately does not — a
pull request owns no checkout of its own. The **transition**: `Runtime.cleanup`
enters that node the way `start` enters the first one, not the way `force`
bypasses a gate, so no verdict is forged and nothing warns about being outside
the model. And the **seam**: `GraphLink.on_cleanup` is the one caller that does
not apply the start gate, because it runs at the end of the life cycle rather
than the beginning.
"""

from __future__ import annotations

import subprocess

import pytest

from the_loop.control import CLEANUP, ControlConfig, ControlStore
from the_loop.graph import hooks  # noqa: F401 — registers the built-in hooks
from the_loop.graph.model import (
    PDLC_ADHOC_LOOP,
    PDLC_CONTRIBUTION_LOOP,
    PDLC_PR_LOOP,
    PDLC_REVIEW_LOOP,
    PDLC_WORK_ITEM_LOOP,
    compile_graph,
    load_graph,
)
from the_loop.graph.runtime import CLEANUP_NODE, Runtime
from the_loop.graph.state import GraphState
from the_loop.graphlink import GraphLink, GraphLinkConfig
from the_loop.sessions import WorkItemRef

REF = WorkItemRef.parse("github:octo/repo#186")
SPEC = "docs/specs/issue-186"

#: Every loop that operates at work-item level — each owns local resources, so
#: each declares the same terminal cleanup node (issue-186, issue-225,
#: issue-279). Only the PR loop stays out: a pull request owns no checkout.
WORK_ITEM_LOOPS = [
    PDLC_WORK_ITEM_LOOP,
    PDLC_CONTRIBUTION_LOOP,
    PDLC_ADHOC_LOOP,
    PDLC_REVIEW_LOOP,
]


# -- the shape -------------------------------------------------------------------


@pytest.mark.parametrize("loop", WORK_ITEM_LOOPS)
def test_every_work_item_loop_declares_a_terminal_cleanup_node(loop):
    node = load_graph(name=loop).nodes[CLEANUP_NODE]
    assert node.terminal is True
    assert node.actor == "code"
    assert node.phase == "cleanup"


def test_the_pull_request_loop_declares_no_cleanup_node():
    """A PR owns no checkout; its endpoint is torn down with the work item's."""
    assert CLEANUP_NODE not in load_graph(name=PDLC_PR_LOOP).nodes


@pytest.mark.parametrize("loop", WORK_ITEM_LOOPS)
def test_nothing_routes_into_cleanup_by_satisfying_a_gate(loop):
    """No inbound edge, like `escalated` — the-loop enters it directly."""
    graph = load_graph(name=loop)
    assert [e for e in graph.edges if e.target == CLEANUP_NODE] == []


def test_complete_is_still_terminal():
    """`await-inner-loops` and `on_pr_close` both read it that way."""
    assert load_graph(name=PDLC_WORK_ITEM_LOOP).nodes["complete"].terminal is True


def test_the_cleanup_phase_is_in_the_configurable_vocabulary():
    import json
    from pathlib import Path

    schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / ".the-loop"
            / "harness-config.schema.json"
        ).read_text(encoding="utf-8")
    )
    phases = schema["properties"]["workflow"]["properties"]["phases"]
    assert "cleanup" in phases["default"]
    assert "cleanup" in phases["items"]["enum"]


# -- Runtime.cleanup -------------------------------------------------------------

GRAPH = {
    "start": "work",
    "nodes": [
        {"id": "work", "phase": "implementation"},
        {"id": "complete", "phase": "complete", "terminal": True},
        {
            "id": CLEANUP_NODE,
            "phase": "cleanup",
            "actor": "code",
            "terminal": True,
            "entry": ["log-entry"],
        },
    ],
    "edges": [{"from": "work", "to": "complete", "on": "pass"}],
}

NO_CLEANUP = {
    "start": "work",
    "nodes": [{"id": "work"}, {"id": "complete", "terminal": True}],
    "edges": [{"from": "work", "to": "complete", "on": "pass"}],
}


@pytest.fixture()
def repo(tmp_path):
    spec = tmp_path / SPEC
    spec.mkdir(parents=True)
    (spec / "execution-log.md").write_text("# Execution Log\n", encoding="utf-8")
    return tmp_path


def runtime_for(repo, graph=GRAPH):
    return Runtime(repo, graph=compile_graph(graph))


def state_of(repo):
    return GraphState.load(repo / SPEC, "issue-186")


def start_at(repo, node="work"):
    state = state_of(repo)
    state.enter(node)
    state.save(repo / SPEC)


def test_it_enters_the_cleanup_node_and_runs_its_entry_chain(repo):
    start_at(repo)

    report = runtime_for(repo).cleanup("issue-186", ref=REF.ref, reason="issue-closed")

    assert report is not None and report.node == CLEANUP_NODE
    assert state_of(repo).current_node == CLEANUP_NODE
    assert CLEANUP_NODE in (repo / SPEC / "execution-log.md").read_text()


def test_it_records_no_force_and_forges_no_verdict(repo):
    """A force warns and rewrites the audit trail; this is not one."""
    start_at(repo)

    runtime_for(repo).cleanup("issue-186", ref=REF.ref)

    state = state_of(repo)
    assert state.forced == []
    assert state.record(CLEANUP_NODE).forced is False
    assert state.record("work").outcome == "", "the node it left keeps its verdict"


def test_entering_from_mid_flight_is_honest_about_where_it_stood(repo):
    """A work item closed unfinished enters from wherever it was."""
    start_at(repo, "work")

    runtime_for(repo).cleanup("issue-186", ref=REF.ref)

    assert state_of(repo).current_node == CLEANUP_NODE
    assert "work" in state_of(repo).nodes


def test_it_is_idempotent(repo):
    start_at(repo)
    rt = runtime_for(repo)
    rt.cleanup("issue-186", ref=REF.ref)
    log_after_first = (repo / SPEC / "execution-log.md").read_text()

    assert rt.cleanup("issue-186", ref=REF.ref) is None
    assert (repo / SPEC / "execution-log.md").read_text() == log_after_first


def test_a_work_item_that_never_entered_the_graph_is_a_no_op(repo):
    assert runtime_for(repo).cleanup("issue-186", ref=REF.ref) is None
    assert state_of(repo).current_node == ""


def test_a_loop_without_a_cleanup_node_is_a_no_op(repo):
    start_at(repo)
    assert runtime_for(repo, NO_CLEANUP).cleanup("issue-186", ref=REF.ref) is None
    assert state_of(repo).current_node == "work"


def test_it_emits_the_node_it_came_from(repo, monkeypatch):
    from the_loop.graph import runtime as runtime_mod

    emitted = []
    monkeypatch.setattr(
        runtime_mod.eventlog, "emit", lambda name, **f: emitted.append((name, f))
    )
    start_at(repo)

    runtime_for(repo).cleanup("issue-186", ref=REF.ref, reason="issue-closed")

    cleaned = [f for name, f in emitted if name == "graph.cleaned"]
    assert cleaned and cleaned[0]["from"] == "work"
    assert cleaned[0]["reason"] == "issue-closed"


# -- GraphLink.on_cleanup --------------------------------------------------------


def checkout(root):
    """A real checkout of the work item's own repo — the link refuses foreign ones."""
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
    spec = root / SPEC
    spec.mkdir(parents=True)
    (spec / "execution-log.md").write_text("# Execution Log\n", encoding="utf-8")
    return root


def test_link_the_cleanup_transition_is_recorded_even_though_the_item_is_disarmed(
    tmp_path,
):
    """The one caller that skips the start gate — it runs at the *end*.

    A cleanup disarms the work item by the very command that asks for it, so
    applying `_awaiting_start` here would make the graph silently skip the
    transition it exists to record.
    """
    root = checkout(tmp_path / "co")
    store = ControlStore(tmp_path / "portable")
    store.record(REF, CLEANUP, source="comment", actor="octocat")
    assert store.start_requested(REF) is False
    link = GraphLink(
        GraphLinkConfig(),
        ControlConfig(require_start_command=True),
        store,
        ["octocat"],
    )
    state = GraphState.load(root / SPEC, "issue-186")
    state.enter("implementation")
    state.save(root / SPEC)

    link.on_cleanup(REF, str(root), reason="cleanup requested")

    assert GraphState.load(root / SPEC, "issue-186").current_node == CLEANUP_NODE


def test_link_a_foreign_checkout_is_still_refused(tmp_path):
    """`require_started=False` widens exactly one gate, not the ownership proof."""
    root = tmp_path / "foreign"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "remote",
            "add",
            "origin",
            "https://github.com/someone/else.git",
        ],
        check=True,
    )
    spec = root / SPEC
    spec.mkdir(parents=True)
    state = GraphState(work_item="issue-186")
    state.enter("implementation")
    state.save(spec)
    link = GraphLink(GraphLinkConfig(), ControlConfig(enabled=False), None, [])

    link.on_cleanup(REF, str(root))

    assert GraphState.load(spec, "issue-186").current_node == "implementation"


def test_link_a_work_item_with_no_spec_directory_is_a_no_op(tmp_path):
    root = tmp_path / "co2"
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
    link = GraphLink(GraphLinkConfig(), ControlConfig(enabled=False), None, [])

    link.on_cleanup(REF, str(root))  # must not raise

    assert not (root / SPEC).exists()
