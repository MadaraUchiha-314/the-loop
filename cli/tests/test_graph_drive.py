"""The graph runs the PDLC — units (issue-148).

The primitive under test is the completion **claim** (`Runtime.complete`): the
one new input that can prompt the graph to move, and everything it must refuse.
Alongside it: the read-only `GraphContext` the dispatcher resolves before any
delivery, the `$graph_context` render, and the `session: inherit` binding.
"""

from __future__ import annotations

import pytest

from the_loop.graph import hooks  # noqa: F401 — registers the shipped hooks
from the_loop.graph.model import compile_graph
from the_loop.graph.runtime import Runtime
from the_loop.graph.state import GraphState, StateLockBusy, state_lock
from the_loop.graphlink import (
    GraphContext,
    GraphLink,
    GraphLinkConfig,
    render_graph_context,
)
from the_loop.control import ControlConfig
from the_loop.sessions import WorkItemRef

GRAPH = {
    "start": "design",
    "nodes": [
        {
            "id": "design",
            "phase": "design",
            "command": "create-design",
            "produces": ["design.md"],
            "exit": [{"hook": "validate-artifacts", "with": {"locked": True}}],
        },
        {"id": "gate", "actor": "human", "required": True, "session": "inherit"},
        {"id": "done", "terminal": True},
    ],
    "edges": [
        {"from": "design", "to": "gate", "on": "pass"},
        {"from": "gate", "to": "done", "on": "approved"},
    ],
}

REF = WorkItemRef.parse("github:octo/repo#1")


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / "issue-1").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def runtime(repo):
    return Runtime(repo, graph=compile_graph(GRAPH))


def _spec(repo):
    return repo / "docs" / "specs" / "issue-1"


def _write_design(repo, status="approved"):
    (_spec(repo) / "design.md").write_text(f"---\nstatus: {status}\n---\n\n# D\n")


# -- Runtime.complete: the claim ------------------------------------------------


def test_a_claim_on_a_satisfied_node_advances(runtime, repo):
    _write_design(repo)
    runtime.start("issue-1")
    result = runtime.complete("issue-1")
    assert result["moved"] is True
    assert result["currentNode"] == "gate"
    assert GraphState.load(_spec(repo), "issue-1").current_node == "gate"


def test_a_claim_is_recorded_in_the_completions_ledger(runtime, repo):
    _write_design(repo)
    runtime.start("issue-1")
    runtime.complete("issue-1", actor="sess-42")
    ledger = GraphState.load(_spec(repo), "issue-1").completions
    assert "design" in ledger and ledger["design"]["by"] == "sess-42"


def test_a_claim_for_unfinished_work_moves_nothing(runtime, repo):
    """Abuse case 2 — a prompt-injected "declare everything done" achieves
    nothing: the chain blocks on the artifacts it would block on anyway."""
    _write_design(repo, status="draft")
    runtime.start("issue-1")
    result = runtime.complete("issue-1")
    assert result["moved"] is False and result["status"] == "block"
    assert GraphState.load(_spec(repo), "issue-1").current_node == "design"


def test_a_claim_before_the_graph_was_entered_is_refused(runtime, repo):
    _write_design(repo)
    result = runtime.complete("issue-1")
    assert result["moved"] is False and result["reason"] == "not-started"


def test_a_replayed_claim_for_a_passed_node_is_a_noop(runtime, repo):
    """R1.4 — redelivery of a claim never rewinds or double-advances."""
    _write_design(repo)
    runtime.start("issue-1")
    assert runtime.complete("issue-1", node="design")["moved"] is True
    replay = runtime.complete("issue-1", node="design")
    assert replay["moved"] is False and replay["reason"] == "already-past"
    assert replay["currentNode"] == "gate"


def test_a_claim_for_a_node_ahead_is_refused_naming_the_current(runtime, repo):
    _write_design(repo)
    runtime.start("issue-1")
    result = runtime.complete("issue-1", node="done")
    assert result["moved"] is False and result["reason"] == "not-current"
    assert "'design'" in result["messages"][0]


def test_a_claim_while_the_lock_is_held_reports_busy(runtime, repo):
    _write_design(repo)
    runtime.start("issue-1")
    with state_lock(_spec(repo)):
        result = runtime.complete("issue-1")
    assert result["moved"] is False and result["reason"] == "busy"


def test_the_lock_itself_times_out_rather_than_blocking(repo):
    with state_lock(_spec(repo)):
        with pytest.raises(StateLockBusy):
            with state_lock(_spec(repo), timeout=0.1):
                pass  # pragma: no cover — must not be reached


# -- GraphContext: the read-only resolve -----------------------------------------


class _TrustingLink(GraphLink):
    """A link whose ownership proof always passes — the checkout under test
    is a tmp dir, not a git clone of the work item's repo."""

    def __init__(self, runtime, **kwargs):
        super().__init__(GraphLinkConfig(enabled=True), **kwargs)
        self._runtime = runtime

    def _checkout_belongs_to(self, root, work_item):
        return True

    def _build_runtime(self, cwd, spec_dir):
        return self._runtime


def _link(repo, runtime):
    return _TrustingLink(runtime, control=ControlConfig(enabled=False))


def test_a_fresh_item_has_no_context(runtime, repo):
    assert _link(repo, runtime).context(REF, str(repo)) is None


def test_a_started_item_reports_its_node(runtime, repo):
    _write_design(repo)
    runtime.start("issue-1")
    ctx = _link(repo, runtime).context(REF, str(repo))
    assert ctx is not None
    assert ctx.current_node == "design" and ctx.phase == "design"
    assert ctx.status == "in-progress" and ctx.actor == "agent"
    assert ctx.next_command == "create-design"
    assert not ctx.at_human_gate


def test_an_item_parked_at_a_human_gate_is_waiting(runtime, repo):
    _write_design(repo)
    runtime.start("issue-1")
    runtime.complete("issue-1")
    runtime.advance("issue-1")  # gate evaluates: no feedback yet → parked
    ctx = _link(repo, runtime).context(REF, str(repo))
    assert ctx is not None and ctx.status == "waiting" and ctx.at_human_gate


def test_a_blocked_item_carries_the_blocking_message(runtime, repo):
    _write_design(repo, status="draft")
    runtime.start("issue-1")
    runtime.advance("issue-1")
    ctx = _link(repo, runtime).context(REF, str(repo))
    assert ctx is not None and ctx.status == "blocked"
    assert any("not locked" in m for m in ctx.messages)


def test_context_is_read_only(runtime, repo):
    _write_design(repo)
    runtime.start("issue-1")
    before = GraphState.load(_spec(repo), "issue-1").as_dict()
    _link(repo, runtime).context(REF, str(repo))
    assert GraphState.load(_spec(repo), "issue-1").as_dict() == before


# -- the $graph_context render ----------------------------------------------------


def test_no_context_renders_empty():
    """R3.4 — an out-of-graph repository gets byte-identical prompts modulo
    the empty substitution."""
    assert render_graph_context(None, "issue-1") == ""


def test_the_render_names_node_status_and_the_complete_verb():
    ctx = GraphContext(
        current_node="design",
        phase="design",
        status="in-progress",
        reason="",
        messages=(),
        next_command="create-design",
        actor="agent",
    )
    block = render_graph_context(ctx, "issue-1")
    assert "node: design (phase: design) — status: in-progress" in block
    assert "`the-loop graph complete issue-1`" in block
    assert "`/the-loop:create-design issue-1`" in block
    assert "not part of the event payload" in block


def test_the_render_carries_a_gate_verdict():
    ctx = GraphContext(
        current_node="gate",
        phase="",
        status="waiting",
        reason="awaiting a human",
        messages=(),
        next_command="",
        actor="human",
    )
    block = render_graph_context(ctx, "issue-1", verdict="approved")
    assert "classified by the gate first: approved" in block


# -- the session binding (D6) ------------------------------------------------------


def test_on_spawn_records_the_session_binding(runtime, repo):
    _write_design(repo)
    _link(repo, runtime).on_spawn(REF, str(repo), session_id="s-9", runner="tmux")
    bound = GraphState.load(_spec(repo), "issue-1").session
    assert bound == {"id": "s-9", "runner": "tmux", "alive": True}


def test_on_close_marks_the_binding_dead(runtime, repo):
    _write_design(repo)
    link = _link(repo, runtime)
    link.on_spawn(REF, str(repo), session_id="s-9", runner="process")
    link.on_close(REF, str(repo))
    bound = GraphState.load(_spec(repo), "issue-1").session
    assert bound is not None and bound["alive"] is False


def test_a_gate_entry_resolves_its_session(runtime, repo, tmp_path):
    """R5.1 — `resolve_session` finally has a caller: entering a human gate
    logs how the gate's session was arrived at."""
    from the_loop import eventlog

    eventlog.configure(source="test", path=str(tmp_path / "events.jsonl"))
    _write_design(repo)
    link = _link(repo, runtime)
    link.on_spawn(REF, str(repo), session_id="s-9", runner="process")
    runtime.complete("issue-1")  # design → gate (a human, session: inherit node)
    records = (tmp_path / "events.jsonl").read_text().splitlines()
    assert any('"graph.gate_session"' in r and '"inherited"' in r for r in records)
