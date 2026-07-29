"""Runtime + the escape hatch (issue-109, R8, R10)."""

from __future__ import annotations

import json

import pytest

from the_loop.graph import hooks  # noqa: F401
from the_loop.graph.model import GraphConfigError, compile_graph
from the_loop.graph.runtime import Runtime, force
from the_loop.graph.state import GraphState

GRAPH = {
    "start": "design",
    "nodes": [
        {
            "id": "design",
            "produces": ["design.md"],
            "exit": [{"hook": "validate-artifacts", "with": {"locked": True}}],
        },
        {"id": "gate", "actor": "human", "required": True},
        {"id": "done", "terminal": True},
    ],
    "edges": [
        {"from": "design", "to": "gate", "on": "pass"},
        {"from": "gate", "to": "done", "on": "approved"},
    ],
}


@pytest.fixture()
def repo(tmp_path):
    spec = tmp_path / "docs" / "specs" / "issue-1"
    spec.mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def runtime(repo):
    return Runtime(repo, graph=compile_graph(GRAPH))


def _write_design(repo, status="approved"):
    (repo / "docs" / "specs" / "issue-1" / "design.md").write_text(
        f"---\nstatus: {status}\n---\n\n# D\n"
    )


def test_a_satisfied_node_advances(runtime, repo):
    _write_design(repo)
    report = runtime.advance("issue-1")
    assert report.status == "pass"
    state = GraphState.load(repo / "docs" / "specs" / "issue-1", "issue-1")
    assert state.current_node == "gate"


def test_an_unsatisfied_node_does_not_advance(runtime, repo):
    _write_design(repo, status="draft")
    report = runtime.advance("issue-1")
    assert report.status == "block"
    state = GraphState.load(repo / "docs" / "specs" / "issue-1", "issue-1")
    assert state.current_node != "gate"


def test_the_same_finding_twice_escalates(runtime, repo):
    _write_design(repo, status="draft")
    assert runtime.advance("issue-1").status == "block"
    assert runtime.advance("issue-1").status == "escalated"


def test_status_reports_every_node(runtime, repo):
    _write_design(repo)
    report = runtime.status("issue-1")
    assert [n.node for n in report.nodes] == ["design", "gate", "done"]


def test_recompute_derives_the_current_node_from_artifacts(runtime, repo):
    """R8.4 — the artifacts are ground truth, not the state file."""
    _write_design(repo, status="draft")
    report = runtime.status("issue-1", recompute=True)
    assert report.current_node == "design"
    assert not report.ok


# -- the escape hatch ----------------------------------------------------------


def test_force_moves_the_pointer(runtime, repo):
    _write_design(repo, status="draft")
    result = force(runtime, "issue-1", "gate", reason="gate is wrong")
    assert result.to_node == "gate"
    state = GraphState.load(repo / "docs" / "specs" / "issue-1", "issue-1")
    assert state.current_node == "gate"
    assert state.nodes["gate"].forced is True


def test_force_does_not_mark_the_bypassed_gate_satisfied(runtime, repo):
    """R10.4 — the heart of it. A force moves the pointer; it never forges a
    verdict. After forcing past an unmet gate, --recompute must STILL report it."""
    _write_design(repo, status="draft")
    force(runtime, "issue-1", "gate", reason="unblocking")

    report = runtime.status("issue-1", recompute=True)
    design = next(n for n in report.nodes if n.node == "design")
    assert not design.satisfied, "the bypassed gate must keep its real verdict"
    assert not report.ok, "CI must still see the work item as unmet"


def test_force_requires_a_reason(runtime, repo):
    with pytest.raises(ValueError, match="reason is required"):
        force(runtime, "issue-1", "gate", reason="   ")


def test_force_refuses_an_unknown_node_and_lists_the_valid_ones(runtime, repo):
    with pytest.raises(GraphConfigError, match="declared nodes are"):
        force(runtime, "issue-1", "nowhere", reason="typo")


def test_force_warns_when_it_bypasses_a_required_node(runtime, repo):
    _write_design(repo)
    result = force(runtime, "issue-1", "gate", reason="skipping the gate")
    assert any("required" in w for w in result.warnings)


def test_force_warns_on_an_undeclared_transition(runtime, repo):
    _write_design(repo)
    result = force(runtime, "issue-1", "done", reason="jumping ahead")
    assert any("not a declared edge" in w for w in result.warnings)


def test_force_is_recorded_in_graph_state(runtime, repo):
    """R10.5 — an escape hatch that leaves no trace is how determinism dies."""
    _write_design(repo)
    force(runtime, "issue-1", "gate", reason="documented reason", actor="@someone")
    data = json.loads(
        (repo / "docs" / "specs" / "issue-1" / "graph-state.json").read_text()
    )
    entry = data["forced"][0]
    assert entry["reason"] == "documented reason"
    assert entry["actor"] == "@someone"
    assert entry["from"] == "design" and entry["to"] == "gate"
    assert entry["at"]


# -- Runtime.start (issue-113) ---------------------------------------------------


def test_start_enters_the_start_node_and_runs_its_entry_chain(repo):
    """AC1/AC2 — beginning a work item is an explicit transition, not an inference."""
    entered = []

    from the_loop.graph.contract import HookResult
    from the_loop.graph.registry import hook

    @hook("record-entry-113")
    def _record(ctx):
        entered.append(ctx.node_id)
        return HookResult.ok("record-entry-113")

    graph = dict(GRAPH)
    graph["nodes"] = [
        {**GRAPH["nodes"][0], "entry": ["record-entry-113"]},
        *GRAPH["nodes"][1:],
    ]
    runtime = Runtime(repo, graph=compile_graph(graph))

    report = runtime.start("issue-1")

    assert report is not None and report.node == "design"
    assert entered == ["design"], "the start node's entry chain must run"
    state = GraphState.load(repo / "docs" / "specs" / "issue-1", "issue-1")
    assert state.current_node == "design"


def test_start_is_idempotent_when_a_pointer_already_exists(runtime, repo):
    """AC3 — starting an already-started work item must never reset it."""
    _write_design(repo)
    runtime.advance("issue-1")  # design -> gate

    assert runtime.start("issue-1") is None

    state = GraphState.load(repo / "docs" / "specs" / "issue-1", "issue-1")
    assert state.current_node == "gate", "start() must not rewind the pointer"


def test_start_persists_the_pointer_before_the_entry_chain_runs(repo):
    """R8.2 — a hook that dies mid-chain must not leave an unrecorded pointer."""
    seen = {}

    from the_loop.graph.contract import HookResult
    from the_loop.graph.registry import hook

    @hook("read-state-113")
    def _read(ctx):
        path = ctx.work_item.spec_dir / "graph-state.json"
        seen["on_disk"] = (
            json.loads(path.read_text())["currentNode"] if path.is_file() else ""
        )
        return HookResult.ok("read-state-113")

    graph = dict(GRAPH)
    graph["nodes"] = [
        {**GRAPH["nodes"][0], "entry": ["read-state-113"]},
        *GRAPH["nodes"][1:],
    ]
    Runtime(repo, graph=compile_graph(graph)).start("issue-1")

    assert seen["on_disk"] == "design"
