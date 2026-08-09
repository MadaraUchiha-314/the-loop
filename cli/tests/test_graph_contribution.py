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
