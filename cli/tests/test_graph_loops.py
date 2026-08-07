"""The two PDLC loops (issue-172, PR #173): pdlc-work-item-loop and pdlc-pr-loop.

The OUTER loop walks a work item through the PDLC; the INNER loop walks one
pull request through the component-scoped subset, in service of the work item.
They meet at exactly one seam — the outer ``implementation`` node's
``await-inner-loops`` gate, which reads the inner loops' checked-in state and
nothing else. These tests pin the seam from both sides: the hook over state
files, the runtime's state separation, and the graphlink entry points the
dispatcher drives.
"""

from __future__ import annotations

import json

import pytest

from the_loop.control import ControlConfig
from the_loop.graph.bootstrap import build_runtime
from the_loop.graph.hooks.loops import (
    PR_LOOPS_DIRNAME,
    await_inner_loops,
    inner_loop_state_dir,
)
from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.model import PDLC_PR_LOOP, PDLC_WORK_ITEM_LOOP, load_graph
from the_loop.graph.state import GraphState
from the_loop.graphlink import GraphLink, GraphLinkConfig
from the_loop.sessions import WorkItemRef
from the_loop.webhook.router import RoutedEvent

WI = WorkItemRef.parse("github:octo/repo#15")
PR = WorkItemRef.parse("github:octo/repo#16")


# -- the graphs themselves ------------------------------------------------------


def test_both_loops_ship_compiled_and_named():
    outer = load_graph()
    inner = load_graph(name=PDLC_PR_LOOP)
    assert outer.name == PDLC_WORK_ITEM_LOOP and outer.start == "brainstorming"
    assert inner.name == PDLC_PR_LOOP and inner.start == "implementation"
    # The inner loop is the same loop with steps skipped: nothing before
    # implementation — those are the work item's, decided once at the outer
    # level — and a human gate plus terminal of its own.
    assert "requirements-definition" not in inner.nodes
    assert "tasks-breakdown" not in inner.nodes
    assert inner.node("pr-approval").actor == "human"
    assert inner.node("complete").terminal
    assert inner.node("security-review").required  # not skippable in either loop


def test_the_outer_implementation_node_awaits_the_inner_loops():
    outer = load_graph()
    assert "await-inner-loops" in outer.node("implementation").exit


# -- the seam: await-inner-loops over checked-in state --------------------------


def _ctx(tmp_path):
    spec = tmp_path / "docs" / "specs" / "issue-15"
    spec.mkdir(parents=True, exist_ok=True)
    item = WorkItem(ref=WI.ref, id="issue-15", spec_dir=spec)
    return HookContext(
        work_item=item,
        node={"id": "implementation"},
        boundary="exit",
        repo=tmp_path,
    )


def _inner_state(spec_dir, pr_number, current):
    state_dir = inner_loop_state_dir(spec_dir, pr_number)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "graph-state.json").write_text(
        json.dumps({"workItem": "issue-15", "currentNode": current})
    )


def test_no_inner_loops_passes_vacuously(tmp_path):
    """A single-session work item — the whole pre-issue-172 world — never waits
    on a loop nobody started."""
    result = await_inner_loops(_ctx(tmp_path))
    assert result.status == "pass"


def test_an_unfinished_inner_loop_holds_the_outer_gate(tmp_path):
    ctx = _ctx(tmp_path)
    _inner_state(ctx.work_item.spec_dir, 16, "verification")
    _inner_state(ctx.work_item.spec_dir, 17, "complete")
    result = await_inner_loops(ctx)
    assert result.status == "wait"
    assert result.data["pending"] == ["pr-16"]


def test_all_inner_loops_complete_releases_the_gate(tmp_path):
    ctx = _ctx(tmp_path)
    _inner_state(ctx.work_item.spec_dir, 16, "complete")
    _inner_state(ctx.work_item.spec_dir, 17, "complete")
    result = await_inner_loops(ctx)
    assert result.status == "pass" and result.data["inner_loops"] == 2


def test_a_corrupt_inner_state_holds_the_gate_rather_than_passing_it(tmp_path):
    """An unreadable inner loop is not a finished inner loop: the outer gate
    stays held, loudly naming the PR — the silent-pass shape issue-124 forbids."""
    ctx = _ctx(tmp_path)
    state_dir = inner_loop_state_dir(ctx.work_item.spec_dir, 16)
    state_dir.mkdir(parents=True)
    (state_dir / "graph-state.json").write_text("{not json")
    result = await_inner_loops(ctx)
    assert result.status == "wait" and result.data["pending"] == ["pr-16"]


# -- the runtime: one spec chain, two state locations ---------------------------


@pytest.fixture()
def repo(tmp_path):
    spec = tmp_path / "docs" / "specs" / "issue-15"
    spec.mkdir(parents=True)
    return tmp_path


def test_bootstrap_selects_the_loop_and_the_state_location(repo):
    outer = build_runtime(repo)
    inner = build_runtime(repo, pr_number=16)
    assert outer.graph.name == PDLC_WORK_ITEM_LOOP and outer.state_subpath == ""
    assert inner.graph.name == PDLC_PR_LOOP
    assert inner.state_subpath == f"{PR_LOOPS_DIRNAME}/pr-16"
    # Artifacts resolve against the SAME spec chain either way; only the state
    # splits. A PR does not get a spec chain of its own.
    item = inner.work_item("issue-15")
    assert item.spec_dir == outer.work_item("issue-15").spec_dir
    assert inner.state_dir(item) == item.spec_dir / PR_LOOPS_DIRNAME / "pr-16"


def test_starting_an_inner_loop_leaves_the_outer_pointer_untouched(repo):
    spec = repo / "docs" / "specs" / "issue-15"
    inner = build_runtime(repo, pr_number=16)
    report = inner.start("issue-15", PR.ref)
    assert report is not None and report.node == "implementation"

    inner_state = GraphState.load(inner_loop_state_dir(spec, 16), "issue-15")
    assert inner_state.current_node == "implementation"
    outer_state = GraphState.load(spec, "issue-15")
    assert outer_state.current_node == ""  # the work item never entered here


def test_two_inner_loops_keep_separate_pointers(repo):
    spec = repo / "docs" / "specs" / "issue-15"
    build_runtime(repo, pr_number=16).start("issue-15", PR.ref)
    build_runtime(repo, pr_number=17).start("issue-15", "github:octo/repo#17")
    assert GraphState.load(inner_loop_state_dir(spec, 16), "issue-15").current_node
    assert GraphState.load(inner_loop_state_dir(spec, 17), "issue-15").current_node


# -- graphlink: the daemon's inner-loop entry points ----------------------------


def _git_repo(path, origin="https://github.com/octo/repo.git"):
    import subprocess

    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", origin], check=True
    )
    return path


@pytest.fixture()
def checkout(tmp_path):
    """A real checkout of the work item's own repo, with its spec dir."""
    _git_repo(tmp_path)
    (tmp_path / "docs" / "specs" / "issue-15").mkdir(parents=True)
    return tmp_path


def _routed_comment(body="looks done"):
    payload = {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 16, "pull_request": {"html_url": "x"}},
        "comment": {"body": body, "user": {"login": "octocat"}},
    }
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id="d-1",
        work_items=[PR],
        payload=payload,
    )


def _real_link():
    return GraphLink(
        GraphLinkConfig(enabled=True), control=ControlConfig(enabled=False)
    )


def test_on_pr_spawn_enters_the_inner_loop_only(checkout):
    link = _real_link()
    link.on_pr_spawn(WI, PR, str(checkout), session_id="s-1", runner="tmux")

    spec = checkout / "docs" / "specs" / "issue-15"
    inner = GraphState.load(inner_loop_state_dir(spec, 16), "issue-15")
    assert inner.current_node == "implementation"
    assert inner.session == {"id": "s-1", "runner": "tmux", "alive": True}
    assert GraphState.load(spec, "issue-15").current_node == ""  # outer untouched


def test_on_pr_event_advances_the_inner_loop_not_the_outer(checkout):
    link = _real_link()
    link.on_pr_spawn(WI, PR, str(checkout), session_id="s-1", runner="tmux")
    link.on_pr_event(WI, PR, str(checkout), _routed_comment())

    spec = checkout / "docs" / "specs" / "issue-15"
    inner = GraphState.load(inner_loop_state_dir(spec, 16), "issue-15")
    assert inner.nodes["implementation"].attempts >= 1
    assert GraphState.load(spec, "issue-15").current_node == ""


def test_a_merged_pr_completes_its_inner_loop_audited_as_forced(checkout):
    link = _real_link()
    link.on_pr_spawn(WI, PR, str(checkout), session_id="s-1", runner="tmux")
    link.on_pr_close(WI, PR, str(checkout), merged=True)

    spec = checkout / "docs" / "specs" / "issue-15"
    inner = GraphState.load(inner_loop_state_dir(spec, 16), "issue-15")
    assert inner.current_node == "complete"
    # A force moves the pointer, never forges a verdict (issue-109 R10): the
    # transition is on the record for `check --recompute` and the PR diff.
    assert inner.forced and "merged" in inner.forced[-1]["reason"]
    # ...and the outer seam now reads this loop as finished.
    ctx = _ctx_for(spec)
    assert await_inner_loops(ctx).status == "pass"


def test_an_unmerged_close_leaves_the_inner_loop_where_it_was(checkout):
    """Abandoned is not finished: the outer gate holding is the process
    noticing, not a bug."""
    link = _real_link()
    link.on_pr_spawn(WI, PR, str(checkout), session_id="s-1", runner="tmux")
    link.on_pr_close(WI, PR, str(checkout), merged=False)

    spec = checkout / "docs" / "specs" / "issue-15"
    inner = GraphState.load(inner_loop_state_dir(spec, 16), "issue-15")
    assert inner.current_node == "implementation"
    assert await_inner_loops(_ctx_for(spec)).status == "wait"


def test_an_inner_loop_prompt_claims_with_pr(checkout):
    """The report-back channel addresses the loop the session walks: an
    inner-loop prompt's claim command carries --pr <n>, or the PR session
    would evaluate the work item's OUTER gates when it reports done."""
    from the_loop.graphlink import render_graph_context

    link = _real_link()
    link.on_pr_spawn(WI, PR, str(checkout), session_id="s-1", runner="tmux")
    ctx = link.pr_context(WI, PR, str(checkout))
    assert ctx is not None and ctx.current_node == "implementation"

    block = render_graph_context(ctx, "issue-15", pr_number=16)
    assert "the-loop graph complete issue-15 --pr 16" in block
    assert "pdlc-pr-loop" in block
    # ...and the outer block is byte-identical to what it always was.
    outer = render_graph_context(ctx, "issue-15")
    assert "the-loop graph complete issue-15`" in outer and "--pr" not in outer


def _ctx_for(spec_dir):
    item = WorkItem(ref=WI.ref, id="issue-15", spec_dir=spec_dir)
    return HookContext(
        work_item=item,
        node={"id": "implementation"},
        boundary="exit",
        repo=spec_dir.parents[2],
    )
