"""Declared skips (issue-177): the graph says what MAY be skipped, a human says
what IS, the runtime records and never forges.

The three-party split is the whole design, so the tests are grouped by party:

* **compile** — the vocabulary is fixed at load: ``skippable`` parsed,
  ``required``×``skippable`` refused, a skippable node without a declared
  ``on: skipped`` edge refused, a ``skipSets`` member outside the vocabulary
  refused (M1); and the shipped loops declare exactly what the spec says (M2).
* **declare** — labels are snapshotted once at graph entry, a later label
  change is inert, an integration outage yields no skips (M6); the CLI verb
  requires a reason and refuses retroactive or non-skippable tokens (M7).
* **route & report** — the pointer routes around declared-skipped nodes on
  their declared edges without running their hooks (M3); ``status`` reports a
  skip with provenance in both modes, and a forged declaration on a protected
  node is inert and surfaced (M4); a later gate over an artifact whose author
  was skipped tolerates its absence but still gates it when present (M5).
"""

from __future__ import annotations

import copy

import pytest

from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.model import (
    GraphConfigError,
    PDLC_PR_LOOP,
    compile_graph,
    load_graph,
)
from the_loop.graph.runtime import Runtime, declare_skips
from the_loop.graph.state import GraphState

WORK_ITEM = "issue-1"

#: A miniature of the shipped shape: two skippable spec nodes (one authoring,
#: one human gate), a non-skippable implementation node that re-gates the
#: authored artifact, and a protected review node.
GRAPH = {
    "start": "requirements",
    "nodes": [
        {
            "id": "requirements",
            "phase": "requirements-definition",
            "skippable": True,
            "produces": ["requirements.md"],
            "entry": ["log-entry"],
            "exit": [{"hook": "validate-artifacts", "with": {"locked": True}}],
        },
        {
            "id": "approval",
            "actor": "human",
            "skippable": True,
            "exit": ["classify-feedback"],
        },
        {
            "id": "tasks",
            "phase": "tasks-breakdown",
            "skippable": True,
            "produces": ["tasks.md"],
            "entry": ["log-entry"],
            "exit": [{"hook": "validate-artifacts", "with": {"locked": True}}],
        },
        {
            "id": "implementation",
            "phase": "implementation",
            "produces": ["tasks.md"],
            "exit": [
                {"hook": "validate-artifacts", "with": {"checkmarks": "complete"}}
            ],
        },
        {"id": "security-review", "required": True, "exit": []},
        {"id": "done", "terminal": True},
    ],
    "edges": [
        {"from": "requirements", "to": "approval", "on": "pass"},
        {"from": "requirements", "to": "approval", "on": "skipped"},
        {"from": "approval", "to": "tasks", "on": "approved"},
        {"from": "approval", "to": "tasks", "on": "skipped"},
        {"from": "tasks", "to": "implementation", "on": "pass"},
        {"from": "tasks", "to": "implementation", "on": "skipped"},
        {"from": "implementation", "to": "security-review", "on": "pass"},
        {"from": "security-review", "to": "done", "on": "pass"},
    ],
    "skipSets": {"spec-chain": ["requirements", "approval", "tasks"]},
}


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def runtime(repo):
    return Runtime(repo, graph=compile_graph(copy.deepcopy(GRAPH)))


def _spec_dir(repo):
    return repo / "docs" / "specs" / WORK_ITEM


def _declare(repo, *nodes, via="label", token=""):
    """A declaration as the two channels record it — written through the state
    API, the way the snapshot and the verb do."""
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    for node in nodes:
        state.skips[node] = {
            "via": via,
            "token": token or node,
            "by": "@owner" if via == "cli" else "",
            "reason": "docs-only" if via == "cli" else "",
            "at": "2026-08-08T00:00:00+00:00",
        }
    state.save(_spec_dir(repo))
    return state


# -- M1: the vocabulary is fixed at compile time --------------------------------


def test_skippable_is_parsed_and_reported():
    graph = compile_graph(copy.deepcopy(GRAPH))
    assert graph.node("requirements").skippable is True
    assert graph.node("implementation").skippable is False
    assert graph.node("requirements").as_mapping()["skippable"] is True


def test_required_and_skippable_is_a_compile_error():
    bad = copy.deepcopy(GRAPH)
    bad["nodes"][4]["skippable"] = True  # security-review is required
    with pytest.raises(GraphConfigError, match="security-review"):
        compile_graph(bad)


def test_a_skippable_node_needs_a_declared_skipped_edge():
    bad = copy.deepcopy(GRAPH)
    bad["edges"] = [e for e in bad["edges"] if e.get("on") != "skipped"]
    with pytest.raises(GraphConfigError, match="on: skipped"):
        compile_graph(bad)


def test_a_skip_set_member_outside_the_vocabulary_is_a_compile_error():
    bad = copy.deepcopy(GRAPH)
    bad["skipSets"] = {"broken": ["implementation"]}
    with pytest.raises(GraphConfigError, match="broken.*implementation"):
        compile_graph(bad)


def test_a_skip_set_member_that_is_not_a_node_is_a_compile_error():
    bad = copy.deepcopy(GRAPH)
    bad["skipSets"] = {"broken": ["nowhere"]}
    with pytest.raises(GraphConfigError, match="nowhere"):
        compile_graph(bad)


def test_expand_skip_tokens_accepts_ids_and_sets_and_rejects_the_rest():
    graph = compile_graph(copy.deepcopy(GRAPH))
    accepted, rejected = graph.expand_skip_tokens(
        ["spec-chain", "requirements", "implementation", "nowhere"]
    )
    assert accepted == {
        "requirements": "spec-chain",
        "approval": "spec-chain",
        "tasks": "spec-chain",
    }
    assert rejected == ["implementation", "nowhere"]


# -- M2: the shipped loops declare exactly what the spec says -------------------


SHIPPABLE = {
    "brainstorming",
    "requirements-definition",
    "requirements-approval",
    "design",
    "design-approval",
    "tasks-breakdown",
}


def test_shipped_outer_loop_marks_exactly_the_spec_chain_skippable():
    graph = load_graph()
    assert {n.id for n in graph.ordered() if n.skippable} == SHIPPABLE
    assert set(graph.skip_sets["spec-chain"]) == SHIPPABLE


def test_shipped_floor_is_not_skippable():
    graph = load_graph()
    for node_id in (
        "test-planning",
        "implementation",
        "verification",
        "self-review",
        "critic-review",
        "security-review",
        "evidence",
        "capability-docs",
        "reviewer-briefing",
        "human-approval",
        "complete",
    ):
        assert not graph.node(node_id).skippable, node_id


def test_shipped_pr_loop_declares_no_skippable_node():
    graph = load_graph(name=PDLC_PR_LOOP)
    assert not any(n.skippable for n in graph.ordered())
    assert not graph.skip_sets


# -- M3: routing — records, runs no hooks, lands on the first real node ---------


def test_start_routes_through_declared_skips(runtime, repo):
    _declare(repo, "requirements", "approval", token="spec-chain")
    report = runtime.start(WORK_ITEM)
    assert report is not None
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.current_node == "tasks"
    assert state.nodes["requirements"].outcome == "skipped"
    assert state.nodes["approval"].outcome == "skipped"


def test_advance_routes_through_skips_after_a_satisfied_node(runtime, repo):
    _declare(repo, "approval", "tasks", via="cli")
    (_spec_dir(repo) / "requirements.md").write_text(
        "---\nstatus: approved\n---\n\n# R\n"
    )
    runtime.start(WORK_ITEM)
    report = runtime.advance(WORK_ITEM)
    assert report.status == "pass"
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.current_node == "implementation"
    assert state.nodes["approval"].outcome == "skipped"
    assert state.nodes["tasks"].outcome == "skipped"


def test_a_skipped_node_gets_no_phase_label_and_no_log_entry(runtime, repo):
    """R3.5 — a skipped node's entry hooks never run; the landing node's do."""
    (_spec_dir(repo) / "execution-log.md").write_text("# log\n")
    _declare(repo, "requirements", "approval")
    runtime.start(WORK_ITEM)
    log = (_spec_dir(repo) / "execution-log.md").read_text()
    assert "entry requirements" not in log
    assert "entry tasks" in log


def test_advance_on_a_fresh_item_lands_past_declared_skips(runtime, repo):
    """The CLI-only path never calls start(); advance must route the same."""
    _declare(repo, "requirements", "approval", "tasks")
    report = runtime.advance(WORK_ITEM)
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert report.node == "implementation"
    assert state.nodes["requirements"].outcome == "skipped"


# -- M4: reporting — skip with provenance, never pass; tamper is inert ----------


def test_status_reports_a_declared_skip_with_provenance(runtime, repo):
    _declare(repo, "requirements", token="spec-chain")
    for recompute in (False, True):
        report = runtime.status(WORK_ITEM, recompute=recompute)
        node = next(n for n in report.nodes if n.node == "requirements")
        assert node.status == "skip"
        assert node.outcome == "skipped"
        assert "label" in " ".join(node.messages)
        assert "spec-chain" in " ".join(node.messages)


def test_a_forged_skip_on_a_protected_node_is_inert_and_surfaced(runtime, repo):
    """R3.3 — the tamper case. security-review is required; a hand-written
    declaration must change nothing and must be called out."""
    _declare(repo, "security-review")
    report = runtime.status(WORK_ITEM, recompute=True)
    node = next(n for n in report.nodes if n.node == "security-review")
    assert node.status != "skip"
    assert any("not skippable" in m for m in node.messages)


def test_a_forged_skip_never_routes_the_pointer(runtime, repo):
    _declare(repo, "security-review")
    (_spec_dir(repo) / "requirements.md").write_text(
        "---\nstatus: approved\n---\n\n# R\n"
    )
    runtime.start(WORK_ITEM)
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.current_node == "requirements"
    assert state.nodes.get("security-review") is None or (
        state.nodes["security-review"].outcome != "skipped"
    )


# -- M5: later gates tolerate a declared absence, and only an absence -----------


def test_implementation_gate_tolerates_tasks_md_skipped_and_absent(runtime, repo):
    _declare(repo, "requirements", "approval", "tasks")
    runtime.start(WORK_ITEM)
    report = runtime.advance(WORK_ITEM)
    assert report.status == "pass", report.messages
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.current_node == "security-review"


def test_implementation_gate_still_gates_a_present_tasks_md(runtime, repo):
    """A declaration never weakens a gate over work that WAS produced."""
    _declare(repo, "requirements", "approval", "tasks")
    (_spec_dir(repo) / "tasks.md").write_text(
        "---\nstatus: approved\n---\n\n- [ ] T1\n"
    )
    runtime.start(WORK_ITEM)
    report = runtime.advance(WORK_ITEM)
    assert report.status == "block"
    assert any("unticked" in m for m in report.messages)


# -- M6: phase selection — the loop asks, an authorized human answers -----------


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


SELECT_GRAPH = {
    "start": "phase-selection",
    "nodes": [
        {
            "id": "phase-selection",
            "phase": "phase-selection",
            "actor": "human",
            "required": True,
            "entry": ["post-phase-selection"],
            "exit": ["classify-phase-selection"],
        },
        *GRAPH["nodes"],
    ],
    "edges": [
        {"from": "phase-selection", "to": "requirements", "on": "selected"},
        *GRAPH["edges"],
    ],
    "skipSets": dict(GRAPH["skipSets"]),
}


@pytest.fixture()
def selecting(repo):
    return Runtime(
        repo,
        graph=compile_graph(copy.deepcopy(SELECT_GRAPH)),
        config={"authorizedUsers": ["@owner"]},
    )


def _reply(body, author="@owner"):
    return {"comments": [{"author": author, "body": body}]}


def test_entry_posts_the_checklist_naming_the_selectable_phases(
    selecting, repo, fake_github
):
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    assert len(fake_github.posted) == 1
    body = fake_github.posted[0]
    assert "the-loop execute" in body
    for node in ("requirements", "approval", "tasks"):
        assert f"- [x] {node}" in body
    # every non-skippable node it will actually walk is named as always-runs —
    # including the ones that carry no phase label.
    for node in ("implementation", "security-review"):
        assert node in body
    assert "the-loop:agent-comment" in body


def test_the_checklist_is_posted_once(selecting, repo, fake_github):
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    fake_github.comments = [{"author": "the-loop", "body": fake_github.posted[0]}]
    selecting.advance(WORK_ITEM, ref="github:o/r#1")  # re-entry finds its own marker
    assert len(fake_github.posted) == 1


def test_the_gate_waits_until_an_authorized_reply_says_execute(
    selecting, repo, fake_github
):
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    report = selecting.advance(
        WORK_ITEM, ref="github:o/r#1", event=_reply("looks fine")
    )
    assert report.status == "wait"
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.current_node == "phase-selection"
    assert state.skips == {}


def test_an_unauthorized_reply_never_selects(selecting, repo, fake_github):
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    report = selecting.advance(
        WORK_ITEM,
        ref="github:o/r#1",
        event=_reply("- [ ] requirements\nthe-loop execute", author="@drive-by"),
    )
    assert report.status == "wait"
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.skips == {}


def test_unticked_phases_become_declared_skips_and_the_loop_starts(
    selecting, repo, fake_github
):
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    selecting.advance(
        WORK_ITEM,
        ref="github:o/r#1",
        event=_reply(
            "- [ ] requirements\n- [ ] approval\n- [x] tasks\n\nthe-loop execute"
        ),
    )
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert set(state.skips) == {"requirements", "approval"}
    assert state.skips["requirements"]["via"] == "selection"
    assert state.skips["requirements"]["by"] == "@owner"
    # requirements/approval routed around; `tasks` was kept, so that is where
    # the pointer lands.
    assert state.current_node == "tasks"
    assert any("phase selection recorded" in p for p in fake_github.posted)


def test_execute_with_no_checklist_runs_the_full_process(selecting, repo, fake_github):
    """Fail closed: a reply that selects nothing removes nothing."""
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    selecting.advance(WORK_ITEM, ref="github:o/r#1", event=_reply("the-loop execute"))
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.skips == {}
    assert state.current_node == "requirements"


def test_unticking_a_protected_phase_is_refused_and_said_so(
    selecting, repo, fake_github
):
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    selecting.advance(
        WORK_ITEM,
        ref="github:o/r#1",
        event=_reply("- [ ] implementation\n- [ ] tasks\nthe-loop execute"),
    )
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert set(state.skips) == {"tasks"}
    assert any("Refused" in p and "implementation" in p for p in fake_github.posted)


def test_a_selection_cannot_excuse_a_node_already_walked(selecting, repo, fake_github):
    """A late reply naming an entered node is ignored for that node — the same
    'a skip is a plan, not an amnesty' rule the CLI verb enforces."""
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    selecting.advance(WORK_ITEM, ref="github:o/r#1", event=_reply("the-loop execute"))
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.current_node == "requirements"  # entered
    declare_skips(
        selecting, WORK_ITEM, ["requirements"], reason="too late", actor="@owner"
    )
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.skips == {}


def test_a_github_outage_leaves_the_gate_waiting_not_open(selecting, repo, monkeypatch):
    def broken(target, config):
        raise RuntimeError("github is down")

    monkeypatch.setattr("the_loop.graph.integrations.resolve", broken)
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    report = selecting.advance(WORK_ITEM, ref="github:o/r#1")
    assert report.status == "wait"
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.current_node == "phase-selection"
    assert state.skips == {}


def test_ticking_in_place_is_the_selection(selecting, repo, fake_github):
    """The owner's ergonomics (PR #178): boxes are ticked on the-loop's own
    comment, and an authorized `the-loop execute` is what makes that state
    theirs."""
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    # the user unticks two boxes on our checklist comment, in place
    posted = fake_github.posted[0]
    fake_github.comments = [
        {
            "author": "the-loop",
            "body": posted.replace("- [x] requirements", "- [ ] requirements").replace(
                "- [x] approval", "- [ ] approval"
            ),
        }
    ]
    selecting.advance(WORK_ITEM, ref="github:o/r#1", event=_reply("the-loop execute"))
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert set(state.skips) == {"requirements", "approval"}
    assert state.skips["requirements"]["by"] == "@owner"
    assert state.decisions["phase-selection"]["via"] == "checklist"


def test_a_checklist_in_the_reply_wins_over_the_boxes(selecting, repo, fake_github):
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    fake_github.comments = [
        {
            "author": "the-loop",
            "body": fake_github.posted[0].replace(
                "- [x] requirements", "- [ ] requirements"
            ),
        }
    ]
    selecting.advance(
        WORK_ITEM,
        ref="github:o/r#1",
        event=_reply("- [ ] tasks\n- [x] requirements\nthe-loop execute"),
    )
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert set(state.skips) == {"tasks"}
    assert state.decisions["phase-selection"]["via"] == "reply"


def test_the_selection_freezes_the_graph_and_publishes_it(selecting, repo, fake_github):
    """The owner's third requirement: the executed graph is recorded, and
    pushed to the portable work-item record through the daemon's sink."""
    published = []
    selecting.config = {
        **selecting.config,
        "frozenGraphSink": lambda frozen: published.append(frozen),
    }
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    selecting.advance(
        WORK_ITEM,
        ref="github:o/r#1",
        event=_reply("- [ ] requirements\nthe-loop execute"),
    )
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    frozen = state.decisions["phase-selection"]["graph"]
    by_id = {n["id"]: n for n in frozen["nodes"]}
    assert by_id["requirements"]["skipped"] is True
    assert by_id["implementation"]["skipped"] is False
    assert by_id["implementation"]["selectable"] is False
    assert [n["id"] for n in frozen["nodes"]] == [
        "phase-selection",
        "requirements",
        "approval",
        "tasks",
        "implementation",
        "security-review",
        "done",
    ]
    assert published == [frozen]


def test_a_failing_frozen_graph_sink_never_gates_the_selection(
    selecting, repo, fake_github
):
    def broken(frozen):
        raise RuntimeError("registry is unavailable")

    selecting.config = {**selecting.config, "frozenGraphSink": broken}
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    report = selecting.advance(
        WORK_ITEM, ref="github:o/r#1", event=_reply("the-loop execute")
    )
    assert report.status == "pass"
    assert GraphState.load(_spec_dir(repo), WORK_ITEM).current_node == "requirements"


def test_the_execute_keyword_is_operator_configurable(repo, fake_github):
    runtime = Runtime(
        repo,
        graph=compile_graph(copy.deepcopy(SELECT_GRAPH)),
        config={"authorizedUsers": ["@owner"], "executeKeyword": "loop go"},
    )
    runtime.start(WORK_ITEM, ref="github:o/r#1")
    assert "loop go" in fake_github.posted[0]
    # the default keyword no longer answers the gate
    assert (
        runtime.advance(
            WORK_ITEM, ref="github:o/r#1", event=_reply("the-loop execute")
        ).status
        == "wait"
    )
    runtime.advance(WORK_ITEM, ref="github:o/r#1", event=_reply("loop go"))
    assert GraphState.load(_spec_dir(repo), WORK_ITEM).current_node == "requirements"


def test_an_answered_gate_stays_answered_for_check(selecting, repo, fake_github):
    """`the-loop check` passes no event on purpose. Without a durable record of
    the decision, every work item would read as stuck at its first node forever
    — so the answer is recorded and the gate honours it."""
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    selecting.advance(
        WORK_ITEM,
        ref="github:o/r#1",
        event=_reply("- [ ] requirements\nthe-loop execute"),
    )
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert "phase-selection" in state.decisions

    for recompute in (False, True):
        report = selecting.status(WORK_ITEM, recompute=recompute)
        gate = next(n for n in report.nodes if n.node == "phase-selection")
        assert gate.status == "pass", gate.messages


def test_the_shipped_loop_starts_at_phase_selection():
    graph = load_graph()
    assert graph.start == "phase-selection"
    node = graph.node("phase-selection")
    assert node.actor == "human" and node.required and not node.skippable
    assert graph.next_node("phase-selection", "selected") == "brainstorming"


# -- M7: the CLI verb — audited, bounded, never retroactive ----------------------


@pytest.fixture()
def quiet_announce(monkeypatch):
    posted = []

    def fake_resolve(target, config):
        class _P:
            def call(self, op, **params):
                posted.append((op, params))
                return {}

        return _P()

    monkeypatch.setattr("the_loop.graph.integrations.resolve", fake_resolve)
    return posted


def test_declare_skips_requires_a_reason(runtime):
    with pytest.raises(ValueError, match="reason is required"):
        declare_skips(runtime, WORK_ITEM, ["requirements"], reason="  ")


def test_declare_skips_records_provenance_and_announces(runtime, repo, quiet_announce):
    result = declare_skips(
        runtime, WORK_ITEM, ["spec-chain"], reason="docs-only", actor="@owner"
    )
    assert result.declared == ["requirements", "approval", "tasks"]
    assert result.rejected == []
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.skips["approval"] == {
        "via": "cli",
        "token": "spec-chain",
        "by": "@owner",
        "reason": "docs-only",
        "at": state.skips["approval"]["at"],
    }
    assert [op for op, _ in quiet_announce] == ["add-comment"]
    body = quiet_announce[0][1]["body"]
    assert "the-loop:agent-comment" in body and "docs-only" in body


def test_declare_skips_refuses_protected_and_unknown_tokens(
    runtime, repo, quiet_announce
):
    result = declare_skips(
        runtime,
        WORK_ITEM,
        ["security-review", "nowhere", "tasks"],
        reason="trying it on",
    )
    assert result.declared == ["tasks"]
    assert {r["token"] for r in result.rejected} == {"security-review", "nowhere"}
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert set(state.skips) == {"tasks"}


def test_declare_skips_refuses_a_node_already_entered_or_passed(
    runtime, repo, quiet_announce
):
    (_spec_dir(repo) / "requirements.md").write_text(
        "---\nstatus: approved\n---\n\n# R\n"
    )
    runtime.start(WORK_ITEM)
    runtime.advance(WORK_ITEM)  # requirements → approval (entered)
    result = declare_skips(
        runtime,
        WORK_ITEM,
        ["requirements", "approval", "tasks"],
        reason="too late for two of these",
    )
    assert result.declared == ["tasks"]
    assert {r["token"] for r in result.rejected} == {"requirements", "approval"}


def test_declared_skips_survive_a_state_round_trip(repo):
    state = _declare(repo, "requirements", via="cli")
    reloaded = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert reloaded.skips == state.skips


# -- the portable record: the frozen graph travels with the work item ----------


def test_the_frozen_graph_lands_in_the_portable_work_item_record(tmp_path):
    """
    Feature: declared skips (issue-177)
      Scenario: the executed graph is part of tracking the work item
        Given a work item whose phase selection has been frozen
        When the daemon's sink records it
        Then it is a section of the work item's PORTABLE record, beside control

    Requirement: docs/specs/issue-177/requirements.md R2.13
    """
    from the_loop.control import ControlStore
    from the_loop.workitem import GRAPH, WorkItemStore

    store = ControlStore(tmp_path)
    frozen = {
        "loop": "pdlc-work-item-loop",
        "workItem": "issue-1",
        "nodes": [
            {"id": "design", "phase": "design", "skipped": True, "selectable": True}
        ],
    }
    store.record_frozen_graph("github:octo/repo#1", frozen)

    read = WorkItemStore(tmp_path).section("github:octo/repo#1", GRAPH)
    assert read == frozen
    # and it survives beside a control record rather than replacing it
    store.record("github:octo/repo#1", "start", actor="@owner")
    assert WorkItemStore(tmp_path).section("github:octo/repo#1", GRAPH) == frozen
