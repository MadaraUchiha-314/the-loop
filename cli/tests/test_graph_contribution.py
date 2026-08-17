"""The contribution loop (issue-185): the-loop joins an existing, in-progress
work item as a contributor — with a goal, success criteria, and phases sized
for an intervention.

Grouped by the seams the design names:

* **the graph** — the shipped ``pdlc-contribution-loop`` compiles, its two
  required gates are the structural invariants, its skip vocabulary and
  routing match the spec.
* **the goal gate** — ``parse_goal`` accepts the documented shape and refuses
  everything else; ``classify-goal`` waits, fails closed on unauthorized or
  self-authored text, freezes an authorized goal with provenance.
* **the keyword** — ``contribute`` parses, arms, and spawn-arms exactly as
  ``start`` does; a comment carrying two different commands is still refused.
* **loop selection** — ``build_runtime(loop=…)`` honours shipped names only;
  ``GraphState.loop`` round-trips and is written at start; resolution is
  state-first, control-record-second; a pre-issue-185 state file reads as the
  default (migration).
* **the walk** — goal-definition → phase-selection with a stubbed GitHub
  integration, both gates releasing only on authorized input (integration).
"""

from __future__ import annotations

import pytest

from the_loop.control import (
    CONTRIBUTE,
    SPAWN_COMMANDS,
    ControlConfig,
    ControlStore,
    parse_command,
)
from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.bootstrap import build_runtime
from the_loop.graph.hooks.goal import parse_goal
from the_loop.graph.model import (
    PDLC_CONTRIBUTION_LOOP,
    PDLC_PR_LOOP,
    PDLC_WORK_ITEM_LOOP,
    SHIPPED_LOOPS,
    load_graph,
)
from the_loop.graph.state import GraphState
from the_loop.sessions import WorkItemRef

WORK_ITEM = "issue-9"
REF = "github:o/r#9"

GOAL_COMMENT = (
    "the-loop contribute\n"
    "Goal: make the retry loop honour the configured backoff\n"
    "Success criteria:\n"
    "- [ ] the flaky-timeout test passes\n"
    "- no change to the public client API\n"
)


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    return tmp_path


def _spec_dir(repo):
    return repo / "docs" / "specs" / WORK_ITEM


class _FakeGitHub:
    """Serves the ticket's comments and records what the-loop posts."""

    def __init__(self, comments=()):
        self.comments = list(comments)
        self.posted = []

    def call(self, op, **params):
        if op == "list-comments":
            return {"comments": list(self.comments)}
        if op == "add-comment":
            self.posted.append(str(params.get("body") or ""))
            return {}
        return {}


@pytest.fixture()
def fake_github(monkeypatch):
    provider = _FakeGitHub()
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve", lambda target, config: provider
    )
    return provider


@pytest.fixture()
def runtime(repo):
    from the_loop.graph.runtime import Runtime

    return Runtime(
        repo,
        graph=load_graph(name=PDLC_CONTRIBUTION_LOOP),
        config={"authorizedUsers": ["@owner"]},
    )


def _reply(body, author="@owner"):
    return {"comments": [{"author": author, "body": body}]}


# -- the graph ---------------------------------------------------------------


def test_the_contribution_loop_compiles_with_the_specified_shape():
    graph = load_graph(name=PDLC_CONTRIBUTION_LOOP)
    assert graph.name == PDLC_CONTRIBUTION_LOOP
    assert graph.start == "goal-definition"
    # The two structural invariants: purpose and phase choice are human acts.
    assert [n.id for n in graph.ordered() if n.required] == [
        "goal-definition",
        "phase-selection",
    ]
    # Everything else this loop walks is the human's to declare away.
    skippable = {n.id for n in graph.ordered() if n.skippable}
    assert skippable == {
        "context-intake",
        "scoped-plan",
        "plan-approval",
        "implementation",
        "verification",
        "self-review",
        "critic-review",
        "security-review",
        "reviewer-briefing",
        "human-approval",
    }
    assert set(graph.skip_sets) == {"plan", "review-chain"}


def test_the_planning_nodes_author_one_artifact_not_a_spec_chain():
    graph = load_graph(name=PDLC_CONTRIBUTION_LOOP)
    produced = {name for n in graph.ordered() for name in n.produces}
    assert produced == {"contribution.md"}


def test_declaring_everything_away_routes_to_human_gates_only():
    """A contained instruction: every selectable phase skipped still yields a
    walkable path goal → selection → … → complete along declared edges."""
    graph = load_graph(name=PDLC_CONTRIBUTION_LOOP)
    node, hops = "context-intake", 0
    while node != "complete":
        nxt = graph.next_node(node, "skipped")
        assert nxt is not None, f"{node} has no skipped edge"
        node, hops = nxt, hops + 1
        assert hops < 20
    assert hops == 10


def test_a_repo_supplied_contribution_graph_is_warned_about(tmp_path, caplog):
    (tmp_path / ".the-loop").mkdir()
    (tmp_path / ".the-loop" / "pdlc-contribution-loop.yaml").write_text("nodes: []")
    with caplog.at_level("WARNING", logger="the-loop.graph"):
        load_graph(repo=tmp_path, name=PDLC_CONTRIBUTION_LOOP)
    assert any("cannot be overridden" in r.message for r in caplog.records)


# -- the goal gate: parsing ---------------------------------------------------


def test_parse_goal_accepts_the_documented_shape():
    parsed = parse_goal(GOAL_COMMENT)
    assert parsed == {
        "goal": "make the retry loop honour the configured backoff",
        "criteria": [
            "the flaky-timeout test passes",
            "no change to the public client API",
        ],
    }


def test_parse_goal_tolerates_markdown_decoration():
    parsed = parse_goal(
        "**Goal:** ship it\n\n**Success criteria:**\n* [x] done means done\n"
    )
    assert parsed is not None
    assert parsed["goal"] == "ship it"
    assert parsed["criteria"] == ["done means done"]


@pytest.mark.parametrize(
    "body",
    [
        "",
        "no goal at all",
        "Goal: something",  # no criteria list
        "Goal: something\nSuccess criteria:\n\nprose, not bullets",
        "Success criteria:\n- [ ] a criterion with no goal",
    ],
)
def test_parse_goal_refuses_incomplete_statements(body):
    assert parse_goal(body) is None


# -- the goal gate: authorization and freezing --------------------------------


def test_the_gate_waits_and_asks_when_no_goal_exists(runtime, repo, fake_github):
    runtime.start(WORK_ITEM, ref=REF)
    assert len(fake_github.posted) == 1
    assert "Success criteria" in fake_github.posted[0]
    assert "the-loop:agent-comment" in fake_github.posted[0]
    report = runtime.advance(WORK_ITEM, ref=REF, event=_reply("carry on"))
    assert report.status == "wait"
    assert GraphState.load(_spec_dir(repo), WORK_ITEM).current_node == "goal-definition"


def test_the_request_is_posted_once(runtime, repo, fake_github):
    runtime.start(WORK_ITEM, ref=REF)
    fake_github.comments = [{"user": {"login": "bot"}, "body": fake_github.posted[0]}]
    runtime.advance(WORK_ITEM, ref=REF)
    assert len(fake_github.posted) == 1


def test_a_goal_in_the_arming_comment_skips_the_request_entirely(
    runtime, repo, fake_github
):
    """The fast path: the goal rode in with `the-loop contribute`, found by
    re-reading the thread — zero extra round trips, zero extra comments."""
    fake_github.comments = [{"user": {"login": "owner"}, "body": GOAL_COMMENT}]
    runtime.start(WORK_ITEM, ref=REF)
    assert all(
        "what should this contribution achieve" not in p for p in fake_github.posted
    )
    runtime.advance(WORK_ITEM, ref=REF)
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.current_node == "phase-selection"
    decision = state.decisions["goal-definition"]
    assert decision["goal"]["by"] == "@owner"
    assert decision["goal"]["criteria"] == [
        "the flaky-timeout test passes",
        "no change to the public client API",
    ]
    assert any("goal recorded" in p for p in fake_github.posted)


def test_an_unauthorized_goal_is_not_read(runtime, repo, fake_github):
    fake_github.comments = [{"user": {"login": "drive-by"}, "body": GOAL_COMMENT}]
    runtime.start(WORK_ITEM, ref=REF)
    report = runtime.advance(
        WORK_ITEM, ref=REF, event=_reply(GOAL_COMMENT, author="@drive-by")
    )
    assert report.status == "wait"
    assert (
        "goal-definition" not in GraphState.load(_spec_dir(repo), WORK_ITEM).decisions
    )


def test_a_self_authored_goal_is_not_read(runtime, repo, fake_github):
    from the_loop.authz import mark_self_authored

    fake_github.comments = [
        {"user": {"login": "owner"}, "body": mark_self_authored(GOAL_COMMENT)}
    ]
    runtime.start(WORK_ITEM, ref=REF)
    report = runtime.advance(WORK_ITEM, ref=REF)
    assert report.status == "wait"


def test_an_authorized_reply_releases_the_gate(runtime, repo, fake_github):
    runtime.start(WORK_ITEM, ref=REF)
    report = runtime.advance(WORK_ITEM, ref=REF, event=_reply(GOAL_COMMENT))
    assert report.outcome == "defined"
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.current_node == "phase-selection"
    # phase-selection's own entry ran: the checklist for THIS graph's rows.
    checklist = fake_github.posted[-1]
    assert "- [x] context-intake" in checklist
    assert "- [x] scoped-plan" in checklist


def test_an_outage_reads_as_no_goal_never_a_guess(runtime, repo, monkeypatch):
    class _Down:
        def call(self, op, **params):
            raise RuntimeError("github is down")

    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve", lambda target, config: _Down()
    )
    runtime.start(WORK_ITEM, ref=REF)
    report = runtime.advance(WORK_ITEM, ref=REF)
    assert report.status == "wait"


# -- the keyword --------------------------------------------------------------


def test_contribute_parses_as_a_whole_token():
    config = ControlConfig()
    assert (
        parse_command("please the-loop contribute here", config).command == CONTRIBUTE
    )
    assert parse_command("the-loop contributed", config).command is None


def test_contribute_plus_another_command_is_refused():
    result = parse_command("the-loop start and the-loop contribute", ControlConfig())
    assert result.ambiguous and result.command is None


def test_contribute_is_arming_and_spawnable(tmp_path):
    store = ControlStore(tmp_path)
    store.record(REF, CONTRIBUTE, actor="owner")
    assert store.start_requested(REF)
    assert CONTRIBUTE in SPAWN_COMMANDS
    store.record(REF, "stop", actor="owner")
    assert not store.start_requested(REF)


def test_the_keyword_is_configurable():
    config = ControlConfig.from_mapping({"keywords": {"contribute": "loopy join in"}})
    assert parse_command("loopy join in", config).command == CONTRIBUTE
    assert parse_command("the-loop contribute", config).command is None


# -- loop selection -----------------------------------------------------------


def test_build_runtime_loads_the_contribution_loop_by_name(repo):
    runtime = build_runtime(repo, loop=PDLC_CONTRIBUTION_LOOP)
    assert runtime.graph.name == PDLC_CONTRIBUTION_LOOP


def test_build_runtime_refuses_a_non_shipped_loop_name(repo, caplog):
    with caplog.at_level("WARNING", logger="the-loop.graph"):
        runtime = build_runtime(repo, loop="../../evil-graph")
    assert runtime.graph.name == PDLC_WORK_ITEM_LOOP


def test_build_runtime_refuses_the_inner_loop_on_the_outer_path(repo):
    assert build_runtime(repo, loop=PDLC_PR_LOOP).graph.name == PDLC_WORK_ITEM_LOOP


def test_start_records_which_loop_the_state_walks(runtime, repo, fake_github):
    runtime.start(WORK_ITEM, ref=REF)
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.loop == PDLC_CONTRIBUTION_LOOP


def test_state_loop_round_trips_and_predates_gracefully(repo):
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.loop == ""  # pre-issue-185 file / fresh item: the default
    state.loop = PDLC_CONTRIBUTION_LOOP
    state.save(_spec_dir(repo))
    assert GraphState.load(_spec_dir(repo), WORK_ITEM).loop == PDLC_CONTRIBUTION_LOOP


def test_core_verbs_resolve_the_recorded_loop(repo):
    from the_loop.core import graphs as core_graphs

    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    state.loop = PDLC_CONTRIBUTION_LOOP
    state.save(_spec_dir(repo))
    shown = core_graphs.check(str(repo), WORK_ITEM)
    assert any(
        n.get("node") == "goal-definition" for n in shown.get("nodes") or []
    ) or ("goal-definition" in str(shown))


def test_core_verbs_fall_back_on_an_invented_loop_name(repo):
    from the_loop.core import graphs as core_graphs

    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    state.loop = "pdlc-made-up-loop"
    state.save(_spec_dir(repo))
    shown = core_graphs.check(str(repo), WORK_ITEM)
    assert "goal-definition" not in str(shown)


def test_graphlink_prefers_state_then_control_record(tmp_path):
    from the_loop.graphlink import GraphLink, GraphLinkConfig
    from the_loop.sessions import WorkItemRef

    store = ControlStore(tmp_path / "portable")
    link = GraphLink(GraphLinkConfig(), control_store=store)
    ref = WorkItemRef.parse(REF)
    spec = tmp_path / "docs" / "specs" / WORK_ITEM
    spec.mkdir(parents=True)

    # Nothing recorded anywhere: the default.
    assert link._outer_loop_name(tmp_path, "docs/specs", WORK_ITEM, ref) == ""
    # Intent before the first start: the control record decides.
    store.record(ref, CONTRIBUTE, actor="owner")
    assert (
        link._outer_loop_name(tmp_path, "docs/specs", WORK_ITEM, ref)
        == PDLC_CONTRIBUTION_LOOP
    )
    # Once started, the state is the fact — a later control change is inert.
    state = GraphState.load(spec, WORK_ITEM)
    state.loop = PDLC_WORK_ITEM_LOOP
    state.save(spec)
    store.record(ref, CONTRIBUTE, actor="owner")
    assert link._outer_loop_name(tmp_path, "docs/specs", WORK_ITEM, ref) == ""
    # And a forged loop name in the agent-writable state reads as the default.
    state.loop = "pdlc-made-up-loop"
    state.save(spec)
    assert link._outer_loop_name(tmp_path, "docs/specs", WORK_ITEM, ref) == ""


def test_every_shipped_loop_is_loadable():
    for name in SHIPPED_LOOPS:
        assert load_graph(name=name).name == name


# -- the uninitialized repository (PR #187 review) ----------------------------
# The target repo may never have adopted the-loop: no `.the-loop/`, no
# harness-config.yaml, no spec-dir convention. The loop must still run — on
# built-in defaults (decision-044) — and must not push its machinery into the
# repository's history: the spec tree is working state, excluded from git, and
# the thread is the plan's review surface.


def test_build_runtime_needs_no_harness_config(tmp_path):
    """A bare checkout yields a working contribution runtime on defaults."""
    runtime = build_runtime(tmp_path, loop=PDLC_CONTRIBUTION_LOOP)
    assert runtime.graph.name == PDLC_CONTRIBUTION_LOOP
    assert runtime.spec_root == "docs/specs"
    assert runtime.config["phaseLabelPrefix"] == "loop:"
    assert runtime.config["notifications"] == {}
    assert runtime.config["repoInitialized"] is False


def test_build_runtime_knows_an_initialized_repo(tmp_path):
    (tmp_path / ".the-loop").mkdir()
    (tmp_path / ".the-loop" / "harness-config.yaml").write_text("workflow: {}\n")
    assert build_runtime(tmp_path).config["repoInitialized"] is True


def _git(repo, *args):
    import subprocess

    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=10
    )


def test_the_walk_runs_and_stays_out_of_git_in_an_unadopted_repo(tmp_path, fake_github):
    """
    Feature: joining an existing work item as a contributor
    Scenario: the target repository never ran the-loop's setup
      Given a git checkout with no `.the-loop/` directory at all
      And the arming comment states a goal and success criteria
      When the contribution loop starts and advances
      Then the two gates run exactly as in an adopted repository
      And the spec tree exists only as ignored working state — nothing the
           contribution PR could carry

    Requirement: docs/specs/issue-185/requirements.md R6
    """
    assert _git(tmp_path, "init", "-q").returncode == 0
    fake_github.comments = [{"user": {"login": "owner"}, "body": GOAL_COMMENT}]
    runtime = build_runtime(
        tmp_path, authorized_users=["@owner"], loop=PDLC_CONTRIBUTION_LOOP
    )
    runtime.start(WORK_ITEM, ref=REF)
    runtime.advance(WORK_ITEM, ref=REF)
    state = GraphState.load(tmp_path / "docs" / "specs" / WORK_ITEM, WORK_ITEM)
    assert state.current_node == "phase-selection"
    assert state.loop == PDLC_CONTRIBUTION_LOOP
    # The tree is structurally uncommittable, not merely uncommitted.
    ignored = _git(tmp_path, "check-ignore", "-q", f"docs/specs/{WORK_ITEM}/x")
    assert ignored.returncode == 0
    assert _git(tmp_path, "status", "--porcelain").stdout.strip() == ""


def test_an_adopted_repos_spec_tree_is_not_excluded(tmp_path, fake_github):
    assert _git(tmp_path, "init", "-q").returncode == 0
    (tmp_path / ".the-loop").mkdir()
    (tmp_path / ".the-loop" / "harness-config.yaml").write_text("workflow: {}\n")
    runtime = build_runtime(
        tmp_path, authorized_users=["@owner"], loop=PDLC_CONTRIBUTION_LOOP
    )
    runtime.start(WORK_ITEM, ref=REF)
    ignored = _git(tmp_path, "check-ignore", "-q", f"docs/specs/{WORK_ITEM}/x")
    assert ignored.returncode != 0


def _publish_ctx(repo_dir, config):
    from the_loop.graph.contract import HookContext, WorkItem

    spec = repo_dir / "docs" / "specs" / WORK_ITEM
    spec.mkdir(parents=True, exist_ok=True)
    ctx = HookContext(
        work_item=WorkItem(ref=REF, id=WORK_ITEM, spec_dir=spec),
        node={"id": "plan-approval"},
        boundary="entry",
        repo=repo_dir,
        config=config,
    )
    ctx.params = {"artifact": "contribution.md"}
    return ctx, spec


def test_the_plan_is_posted_to_the_thread_when_the_repo_is_unadopted(
    tmp_path, fake_github
):
    from the_loop.graph.hooks.sideeffects import publish_artifact

    ctx, spec = _publish_ctx(tmp_path, {"repoInitialized": False})
    (spec / "contribution.md").write_text("## Goal\n\nship it\n")
    result = publish_artifact(ctx)
    assert result.status == "pass" and result.data["posted"] is True
    assert len(fake_github.posted) == 1
    assert "ship it" in fake_github.posted[0]
    assert "the-loop:agent-comment" in fake_github.posted[0]


def test_the_plan_stays_off_the_thread_in_an_adopted_repo(tmp_path, fake_github):
    """The no-bloat rule holds where the checked-in file is the surface."""
    from the_loop.graph.hooks.sideeffects import publish_artifact

    ctx, spec = _publish_ctx(tmp_path, {"repoInitialized": True})
    (spec / "contribution.md").write_text("## Goal\n\nship it\n")
    assert publish_artifact(ctx).status == "skip"
    assert fake_github.posted == []


def test_a_declared_away_plan_publishes_nothing_and_blocks_nothing(
    tmp_path, fake_github
):
    from the_loop.graph.hooks.sideeffects import publish_artifact

    ctx, _ = _publish_ctx(tmp_path, {"repoInitialized": False})
    assert publish_artifact(ctx).status == "skip"
    assert fake_github.posted == []


# -- the walk (integration) ---------------------------------------------------


class TestContributionWalk:
    def test_goal_then_selection_release_only_on_authorized_input(
        self, runtime, repo, fake_github
    ):
        """
        Feature: joining an existing work item as a contributor
        Scenario: the two required gates release in order, on authorized input
          Given an in-progress work item armed with `the-loop contribute`
          And the arming comment states a goal and success criteria
          When the contribution loop starts and advances
          Then goal-definition freezes the goal and phase-selection asks its
               checklist
          And an unauthorized `the-loop execute` leaves the gate waiting
          And an authorized one starts the walk at context-intake

        Requirement: docs/specs/issue-185/requirements.md R2, R4.1
        """
        fake_github.comments = [{"user": {"login": "owner"}, "body": GOAL_COMMENT}]
        runtime.start(WORK_ITEM, ref=REF)
        runtime.advance(WORK_ITEM, ref=REF)  # goal freezes; selection asks
        state = GraphState.load(_spec_dir(repo), WORK_ITEM)
        assert state.current_node == "phase-selection"
        assert state.loop == PDLC_CONTRIBUTION_LOOP

        report = runtime.advance(
            WORK_ITEM, ref=REF, event=_reply("the-loop execute", author="@drive-by")
        )
        assert report.status == "wait"

        runtime.advance(WORK_ITEM, ref=REF, event=_reply("the-loop execute"))
        state = GraphState.load(_spec_dir(repo), WORK_ITEM)
        assert state.current_node == "context-intake"
        assert state.skips == {}  # boxes untouched: the full intervention runs

    def test_a_contained_instruction_keeps_only_what_was_ticked(
        self, runtime, repo, fake_github
    ):
        """
        Feature: joining an existing work item as a contributor
        Scenario: a small contained instruction runs almost nothing
          Given the goal gate has been answered
          When the authorized reply unticks the plan and review phases
          Then the pointer routes to implementation with every skip attributed

        Requirement: docs/specs/issue-185/requirements.md R4.3
        """
        fake_github.comments = [{"user": {"login": "owner"}, "body": GOAL_COMMENT}]
        runtime.start(WORK_ITEM, ref=REF)
        runtime.advance(WORK_ITEM, ref=REF)
        runtime.advance(
            WORK_ITEM,
            ref=REF,
            event=_reply(
                "- [ ] context-intake\n- [ ] scoped-plan\n- [ ] plan-approval\n"
                "- [x] implementation\n- [x] verification\n"
                "- [ ] self-review\n- [ ] critic-review\n- [ ] security-review\n"
                "- [ ] reviewer-briefing\n- [x] human-approval\n"
                "the-loop execute"
            ),
        )
        state = GraphState.load(_spec_dir(repo), WORK_ITEM)
        assert state.current_node == "implementation"
        assert set(state.skips) == {
            "context-intake",
            "scoped-plan",
            "plan-approval",
            "self-review",
            "critic-review",
            "security-review",
            "reviewer-briefing",
        }
        assert all(s["by"] == "@owner" for s in state.skips.values())


# -- no outer loop to place (issue-199) ---------------------------------------


class _Routed:
    """The one shape :func:`comments_from` reads off an ingress event."""

    def __init__(self, body, author="owner"):
        self.event = "issue_comment"
        self.payload = {"comment": {"body": body, "user": {"login": author}}}


def _contribution_link(runtime):
    """A GraphLink whose ownership proof passes and whose runtime is the
    contribution loop's — the daemon seam, without a git clone."""
    from the_loop.graphlink import GraphLink, GraphLinkConfig

    class _TrustingLink(GraphLink):
        def _checkout_belongs_to(self, root, work_item):
            return True

        def _outer_loop_name(self, root, spec_dir, item_id, work_item):
            return PDLC_CONTRIBUTION_LOOP

        def _build_runtime(self, cwd, spec_dir, pr_number=None, pr_repo="", loop=""):
            assert loop == PDLC_CONTRIBUTION_LOOP
            return runtime

    return _TrustingLink(
        GraphLinkConfig(enabled=True), control=ControlConfig(enabled=False)
    )


def test_the_contribution_checklist_offers_no_surface_row(runtime, repo, fake_github):
    """R1 — a loop with no outer loop is not asked where to put one."""
    from the_loop.graph.hooks.selection import SURFACE_TOKEN

    fake_github.comments = [{"user": {"login": "owner"}, "body": GOAL_COMMENT}]
    runtime.start(WORK_ITEM, ref=REF)
    runtime.advance(WORK_ITEM, ref=REF)  # goal freezes → phase-selection asks
    checklist = fake_github.posted[-1]
    assert "which phases does this work item need" in checklist
    assert SURFACE_TOKEN not in checklist
    assert "Where should the outer loop happen?" not in checklist
    assert "There is no outer loop to place on this one" in checklist


def test_the_outer_loops_checklist_still_asks_the_question(repo, fake_github):
    """The other side of R1: nothing about the work-item loop changes."""
    from the_loop.graph.hooks.selection import SURFACE_TOKEN
    from the_loop.graph.runtime import Runtime

    outer = Runtime(
        repo,
        graph=load_graph(name=PDLC_WORK_ITEM_LOOP),
        config={"authorizedUsers": ["@owner"]},
    )
    outer.start(WORK_ITEM, ref=REF)
    checklist = fake_github.posted[-1]
    assert f"- [ ] `{SURFACE_TOKEN}`" in checklist
    assert "Where should the outer loop happen?" in checklist


def test_the_contribution_checklist_still_asks_how_many_pr_sessions(
    runtime, repo, fake_github
):
    """issue-260, R1.5 — unlike the surface row, this question has a true answer
    here: a contribution's pull request is usually in somebody else's
    repository, which is the case the modes differ most about."""
    fake_github.comments = [{"user": {"login": "owner"}, "body": GOAL_COMMENT}]
    runtime.start(WORK_ITEM, ref=REF)
    runtime.advance(WORK_ITEM, ref=REF)
    checklist = fake_github.posted[-1]
    assert "How many sessions should this work item's pull requests get?" in checklist
    assert "- [x] `pr-sessions-cross-repository`" in checklist


def test_a_ticked_surface_row_in_a_contributions_reply_changes_nothing(
    runtime, repo, fake_github
):
    """R1.3 — not asked, not read: the token is inert on a contribution,
    however it reaches the gate."""
    fake_github.comments = [{"user": {"login": "owner"}, "body": GOAL_COMMENT}]
    runtime.start(WORK_ITEM, ref=REF)
    runtime.advance(WORK_ITEM, ref=REF)
    runtime.advance(
        WORK_ITEM,
        ref=REF,
        event=_reply("- [x] outer-loop-on-pull-request\nthe-loop execute"),
    )
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.current_node == "context-intake"
    assert state.surface == ""  # nothing chosen, because nothing was offered
    frozen = state.decisions["phase-selection"]["graph"]
    assert frozen["loop"] == PDLC_CONTRIBUTION_LOOP and frozen["surface"] == ""
    assert "phase-selection" not in state.skips  # and it declared no phase away
    confirmation = next(
        p for p in fake_github.posted if "phase selection recorded" in p
    )
    assert "outer loop happens" not in confirmation


def test_the_arming_comment_reaches_the_goal_gate_at_spawn(runtime, repo, fake_github):
    """R2 — `the-loop contribute` alone moves the item to phase-selection.

    The arming comment is the one comment a gate can never be handed later:
    the control path executes it instead of forwarding it. So the spawn hands
    it over, and no second command is needed.
    """
    fake_github.comments = [{"user": {"login": "owner"}, "body": GOAL_COMMENT}]
    link = _contribution_link(runtime)
    link.on_spawn(
        WorkItemRef.parse(REF),
        str(repo),
        session_id="s-1",
        runner="tmux",
        routed=_Routed(GOAL_COMMENT),
    )
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.current_node == "phase-selection"
    assert state.decisions["goal-definition"]["goal"]["by"] == "@owner"
    assert any("which phases does this work item need" in p for p in fake_github.posted)
    # The binding is still recorded, and by the session that was spawned.
    assert (state.session or {})["id"] == "s-1"


def test_a_spawn_with_no_goal_parks_the_gate_with_its_reason(
    runtime, repo, fake_github
):
    """R2.2 — waiting is the ordinary outcome, and now it says so: the pointer
    stays put, parked with the question on it."""
    link = _contribution_link(runtime)
    link.on_spawn(
        WorkItemRef.parse(REF), str(repo), routed=_Routed("thanks, looks useful")
    )
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.current_node == "goal-definition"
    assert "goal and success criteria" in str((state.parked or {}).get("reason") or "")


def test_a_respawn_re_evaluates_nothing(runtime, repo, fake_github):
    """R2.3 — only a FRESH entry evaluates: a respawn re-records the binding
    and leaves the pointer exactly where it was."""
    link = _contribution_link(runtime)
    link.on_spawn(WorkItemRef.parse(REF), str(repo), routed=_Routed("no goal here"))
    before = GraphState.load(_spec_dir(repo), WORK_ITEM).as_dict()
    # Answerable now — and still not answered here: a respawn is not an event.
    fake_github.comments = [{"user": {"login": "owner"}, "body": GOAL_COMMENT}]
    link.on_spawn(
        WorkItemRef.parse(REF),
        str(repo),
        session_id="s-2",
        routed=_Routed(GOAL_COMMENT),
    )
    after = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert after.current_node == "goal-definition"
    assert after.as_dict()["nodes"] == before["nodes"]
