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
    declared_repos,
    inner_loop_state_dir,
    repo_state_key,
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
    assert outer.name == PDLC_WORK_ITEM_LOOP and outer.start == "phase-selection"
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


def _ctx(tmp_path, config=None):
    spec = tmp_path / "docs" / "specs" / "issue-15"
    spec.mkdir(parents=True, exist_ok=True)
    item = WorkItem(ref=WI.ref, id="issue-15", spec_dir=spec)
    return HookContext(
        work_item=item,
        node={"id": "implementation"},
        boundary="exit",
        repo=tmp_path,
        config=config or {},
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


# -- several repositories, one work item (issue-183) -----------------------------


def _log(spec_dir, repos=None):
    """The work item's execution log, optionally declaring its repositories."""
    front = ["---", "type: execution-log", "workItem: issue-15"]
    if repos is not None:
        front.append("repos:")
        front.extend(f"  - {repo}" for repo in repos)
    front += ["---", "", "# Execution Log", ""]
    (spec_dir / "execution-log.md").write_text("\n".join(front), encoding="utf-8")


def _inner_state_in(spec_dir, repo, pr_number, current):
    state_dir = inner_loop_state_dir(spec_dir, pr_number, repo)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "graph-state.json").write_text(
        json.dumps({"workItem": "issue-15", "currentNode": current})
    )


def test_repo_state_key_qualifies_a_pull_request_by_repository():
    assert repo_state_key("octo/infra") == "octo__infra"
    assert (
        repo_state_key("ghe.corp.example/octo/infra") == "ghe.corp.example__octo__infra"
    )


@pytest.mark.parametrize(
    "repo",
    [
        "../../etc",
        "a/../b",
        "a//b",
        "octo",
        "",
        "octo/repo/../..",
        "a\\..\\b",
        "octo/re po",
    ],
)
def test_repo_state_key_rejects_traversal_and_junk(repo):
    """A repository name becomes a DIRECTORY name, and it arrives from a webhook
    payload or an operator's --pr-repo. It is rejected, never sanitized: a name
    quietly rewritten into a valid one files one repo's state under another's."""
    with pytest.raises(ValueError):
        repo_state_key(repo)


def test_the_origin_repos_layout_is_unchanged_back_compat(tmp_path):
    """No work item in flight has to be migrated to gain the feature."""
    spec = tmp_path / "spec"
    assert inner_loop_state_dir(spec, 16) == spec / PR_LOOPS_DIRNAME / "pr-16"
    assert (
        inner_loop_state_dir(spec, 7, "octo/infra")
        == spec / PR_LOOPS_DIRNAME / "octo__infra" / "pr-7"
    )


def test_a_contributing_repos_loop_holds_the_outer_gate(tmp_path):
    ctx = _ctx(tmp_path)
    _inner_state(ctx.work_item.spec_dir, 16, "complete")
    _inner_state_in(ctx.work_item.spec_dir, "octo/infra", 7, "verification")
    result = await_inner_loops(ctx)
    assert result.status == "wait"
    assert result.data["pending"] == ["octo__infra/pr-7"]


def test_two_repositories_pull_request_seven_do_not_collide(tmp_path):
    ctx = _ctx(tmp_path)
    _inner_state_in(ctx.work_item.spec_dir, "octo/infra", 7, "complete")
    _inner_state_in(ctx.work_item.spec_dir, "octo/app", 7, "self-review")
    result = await_inner_loops(ctx)
    assert result.status == "wait" and result.data["pending"] == ["octo__app/pr-7"]
    assert result.data["inner_loops"] == 2


def test_declared_repos_are_read_from_the_execution_log(tmp_path):
    ctx = _ctx(tmp_path)
    _log(ctx.work_item.spec_dir, ["octo/app", "octo/infra"])
    assert declared_repos(ctx.work_item.spec_dir) == ["octo/app", "octo/infra"]
    _log(ctx.work_item.spec_dir)
    assert declared_repos(ctx.work_item.spec_dir) == []


def test_await_waits_for_a_declared_repo_with_no_loop(tmp_path):
    """A contribution that was PLANNED and never opened is not an absent one:
    without this, `repos:` would be prose and the gate would pass vacuously."""
    ctx = _ctx(tmp_path, config={"originRepo": "octo/repo"})
    _log(ctx.work_item.spec_dir, ["octo/repo", "octo/infra"])
    _inner_state(ctx.work_item.spec_dir, 16, "complete")
    result = await_inner_loops(ctx)
    assert result.status == "wait"
    assert result.data["missing_repos"] == ["octo/infra"]
    assert "octo/infra" in result.messages[0].text


def test_every_declared_repo_with_a_finished_loop_releases_the_gate(tmp_path):
    ctx = _ctx(tmp_path, config={"originRepo": "octo/repo"})
    _log(ctx.work_item.spec_dir, ["octo/repo", "octo/infra"])
    _inner_state(ctx.work_item.spec_dir, 16, "complete")
    _inner_state_in(ctx.work_item.spec_dir, "octo/infra", 7, "complete")
    result = await_inner_loops(ctx)
    assert result.status == "pass" and result.data["declared"] == 2


def test_a_declared_origin_repo_needs_a_configured_origin(tmp_path):
    """Without `ticketing.github`, a top-level pr-<n>/ cannot be attributed to a
    repository — so the gate says so rather than guessing which loop was meant."""
    ctx = _ctx(tmp_path)
    _log(ctx.work_item.spec_dir, ["octo/repo"])
    _inner_state(ctx.work_item.spec_dir, 16, "complete")
    result = await_inner_loops(ctx)
    assert result.status == "wait"
    assert "ticketing.github" in result.messages[0].text


def test_a_malformed_declared_repo_blocks_rather_than_waits(tmp_path):
    """Waiting for `../../etc` would wait forever: a fault in a checked-in file
    is a block, not work in progress."""
    ctx = _ctx(tmp_path)
    _log(ctx.work_item.spec_dir, ["../../etc"])
    result = await_inner_loops(ctx)
    assert result.status == "block"


def test_declaring_nothing_keeps_the_pre_issue_183_behaviour(tmp_path):
    ctx = _ctx(tmp_path)
    _log(ctx.work_item.spec_dir)
    assert await_inner_loops(ctx).status == "pass"


def test_bootstrap_qualifies_the_state_path_by_repository(repo):
    inner = build_runtime(repo, pr_number=7, pr_repo="octo/infra")
    assert inner.state_subpath == f"{PR_LOOPS_DIRNAME}/octo__infra/pr-7"
    item = inner.work_item("issue-15")
    # Still the ONE spec chain, in the origin repository's checkout.
    assert item.spec_dir == build_runtime(repo).work_item("issue-15").spec_dir


def test_bootstrap_refuses_a_hostile_repository(repo):
    with pytest.raises(ValueError):
        build_runtime(repo, pr_number=7, pr_repo="../../etc")


def test_bootstrap_resolves_the_outer_loop_surface_and_origin(tmp_path):
    (tmp_path / ".the-loop").mkdir()
    (tmp_path / ".the-loop" / "harness-config.yaml").write_text(
        "ticketing:\n  github:\n    owner: octo\n    repo: repo\n"
        "workflow:\n  outerLoop:\n    surface: issue\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "specs" / "issue-15").mkdir(parents=True)
    runtime = build_runtime(tmp_path)
    assert runtime.config["outerLoopSurface"] == "issue"
    assert runtime.config["originRepo"] == "octo/repo"


def test_bootstrap_defaults_the_surface_to_pull_request(repo):
    assert build_runtime(repo).config["outerLoopSurface"] == "pull-request"


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


def test_a_cross_repo_inner_loop_prompt_claims_with_both(checkout):
    """A claim without --pr-repo would evaluate a DIFFERENT loop: pr-7 in the
    origin repository, not pr-7 in the contributing one (issue-183)."""
    from the_loop.graphlink import render_graph_context

    link = _real_link()
    foreign = WorkItemRef.parse("github:octo/infra#7")
    link.on_pr_spawn(WI, foreign, str(checkout), session_id="s-1", runner="tmux")
    ctx = link.pr_context(WI, foreign, str(checkout))
    assert ctx is not None

    block = render_graph_context(ctx, "issue-15", pr_number=7, pr_repo="octo/infra")
    assert "the-loop graph complete issue-15 --pr 7 --pr-repo octo/infra" in block
    assert "the inner loop always runs on its PR" in block
    # The origin repository's own PR keeps the shipped, unqualified claim.
    same_repo = render_graph_context(ctx, "issue-15", pr_number=7)
    assert "the-loop graph complete issue-15 --pr 7`" in same_repo


def test_the_outer_prompt_names_the_declared_surface(checkout):
    from the_loop.graph.bootstrap import build_runtime as _build
    from the_loop.graphlink import GraphContext, render_graph_context

    (checkout / ".the-loop").mkdir(exist_ok=True)
    (checkout / ".the-loop" / "harness-config.yaml").write_text(
        "workflow:\n  outerLoop:\n    surface: issue\n", encoding="utf-8"
    )
    surface = _build(checkout).config["outerLoopSurface"]
    ctx = GraphContext(
        current_node="design",
        phase="design",
        status="in-progress",
        reason="",
        messages=(),
        next_command="create-design",
        actor="agent",
        surface=surface,
    )
    block = render_graph_context(ctx, "issue-15")
    assert "iterate the outer loop's artifacts on: the ticket" in block
    assert "--pr" not in block


# -- the graph assigns: deliver-assignment (issue-172, "who is in charge?") -----


def test_deliver_assignment_skips_without_a_channel(tmp_path):
    """The CLI path: the claiming session reads the envelope; nothing pushes."""
    from the_loop.graph.hooks.assignment import deliver_assignment

    result = deliver_assignment(_ctx(tmp_path))
    assert result.status == "skip"


def test_deliver_assignment_renders_the_nodes_work_and_the_claim_command(tmp_path):
    from the_loop.graph.contract import HookContext, WorkItem
    from the_loop.graph.hooks.assignment import deliver_assignment

    delivered = []
    spec = tmp_path / "docs" / "specs" / "issue-15"
    spec.mkdir(parents=True, exist_ok=True)
    ctx = HookContext(
        work_item=WorkItem(ref=WI.ref, id="issue-15", spec_dir=spec),
        node={
            "id": "design",
            "phase": "design",
            "produces": ["design.md"],
            "command": "create-design",
        },
        boundary="entry",
        repo=tmp_path,
        config={"assignmentDeliver": lambda text: delivered.append(text) or True},
    )
    assert deliver_assignment(ctx).status == "pass"
    (text,) = delivered
    assert "you are now at node: design" in text
    assert "produce: design.md" in text
    assert "/the-loop:create-design issue-15" in text
    assert "the-loop graph complete issue-15`" in text and "--pr" not in text


def test_deliver_assignment_addresses_the_inner_loop(tmp_path):
    from the_loop.graph.contract import HookContext, WorkItem
    from the_loop.graph.hooks.assignment import deliver_assignment

    delivered = []
    spec = tmp_path / "docs" / "specs" / "issue-15"
    spec.mkdir(parents=True, exist_ok=True)
    ctx = HookContext(
        work_item=WorkItem(ref=WI.ref, id="issue-15", spec_dir=spec),
        node={"id": "implementation", "phase": "implementation"},
        boundary="entry",
        repo=tmp_path,
        config={
            "assignmentDeliver": lambda text: delivered.append(text) or True,
            "assignmentPr": 16,
        },
    )
    assert deliver_assignment(ctx).status == "pass"
    (text,) = delivered
    assert "pull request #16's pdlc-pr-loop" in text
    assert "the-loop graph complete issue-15 --pr 16" in text


def _assignment(tmp_path, node, config):
    from the_loop.graph.contract import HookContext, WorkItem
    from the_loop.graph.hooks.assignment import deliver_assignment

    delivered = []
    spec = tmp_path / "docs" / "specs" / "issue-15"
    spec.mkdir(parents=True, exist_ok=True)
    ctx = HookContext(
        work_item=WorkItem(ref=WI.ref, id="issue-15", spec_dir=spec),
        node=node,
        boundary="entry",
        repo=tmp_path,
        config={
            "assignmentDeliver": lambda text: delivered.append(text) or True,
            **config,
        },
    )
    assert deliver_assignment(ctx).status == "pass"
    return delivered[0]


def test_the_assignment_names_the_declared_outer_surface(tmp_path):
    """A session is TOLD where to iterate rather than inferring it (issue-183)."""
    node = {"id": "design", "phase": "design", "produces": ["design.md"]}
    on_issue = _assignment(tmp_path, node, {"outerLoopSurface": "issue"})
    assert "iterate it on: the ticket" in on_issue
    assert "do not open a pull request just to carry the spec chain" in on_issue

    on_pr = _assignment(tmp_path, node, {"outerLoopSurface": "pull-request"})
    assert (
        "the work item's pull request in the repository the ticket was created in"
        in (on_pr)
    )


def test_an_inner_loop_assignment_has_no_surface_to_choose(tmp_path):
    """R2.7: a pull request's loop runs on that pull request. No setting moves it."""
    text = _assignment(
        tmp_path,
        {"id": "implementation", "produces": ["tasks.md"]},
        {
            "assignmentPr": 7,
            "assignmentPrRepo": "octo/infra",
            "outerLoopSurface": "issue",
        },
    )
    assert "iterate it on: this pull request" in text
    assert "in octo/infra" in text
    # ...and the claim addresses THAT loop, not a pr-7 in the origin repository.
    assert "the-loop graph complete issue-15 --pr 7 --pr-repo octo/infra" in text


def test_a_failing_channel_never_gates_the_node(tmp_path):
    from the_loop.graph.contract import HookContext, WorkItem
    from the_loop.graph.hooks.assignment import deliver_assignment

    spec = tmp_path / "docs" / "specs" / "issue-15"
    spec.mkdir(parents=True, exist_ok=True)

    def boom(text):
        raise RuntimeError("tmux went away")

    ctx = HookContext(
        work_item=WorkItem(ref=WI.ref, id="issue-15", spec_dir=spec),
        node={"id": "design"},
        boundary="entry",
        repo=tmp_path,
        config={"assignmentDeliver": boom},
    )
    assert deliver_assignment(ctx).status == "skip"  # reported, never a block


def test_the_graph_assigns_on_entering_the_inner_loop(checkout):
    """End to end through graphlink: entering a node pushes its assignment into
    the loop's bound session — the graph assigns, the session works."""
    pushed = []

    def sink(work_item, pr_number, text):
        pushed.append((work_item.ref, pr_number, text))
        return True

    link = GraphLink(
        GraphLinkConfig(enabled=True),
        control=ControlConfig(enabled=False),
        assignment_sink=sink,
    )
    link.on_pr_spawn(WI, PR, str(checkout), session_id="s-1", runner="tmux")

    assert len(pushed) == 1
    ref, pr_number, text = pushed[0]
    assert (ref, pr_number) == (WI.ref, 16)
    assert "you are now at node: implementation" in text
    assert "the-loop graph complete issue-15 --pr 16" in text


def test_the_outer_loop_assigns_without_a_pr(checkout):
    pushed = []

    def sink(work_item, pr_number, text):
        pushed.append((work_item.ref, pr_number, text))
        return True

    link = GraphLink(
        GraphLinkConfig(enabled=True),
        control=ControlConfig(enabled=False),
        assignment_sink=sink,
    )
    link.on_spawn(WI, str(checkout), session_id="s-1", runner="tmux")

    assert len(pushed) == 1
    ref, pr_number, text = pushed[0]
    assert (ref, pr_number) == (WI.ref, None)
    # issue-177: the outer loop now opens on a HUMAN gate, so the session is
    # told to wait rather than to claim it.
    assert "you are now at node: phase-selection" in text
    assert "HUMAN gate" in text and "Do not claim it" in text
    assert "the-loop graph complete" not in text


def _ctx_for(spec_dir):
    item = WorkItem(ref=WI.ref, id="issue-15", spec_dir=spec_dir)
    return HookContext(
        work_item=item,
        node={"id": "implementation"},
        boundary="exit",
        repo=spec_dir.parents[2],
    )
