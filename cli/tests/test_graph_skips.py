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


SPEC_CHAIN = {
    "brainstorming",
    "requirements-definition",
    "requirements-approval",
    "design",
    "test-planning",
    "design-approval",
    "tasks-breakdown",
}

REVIEW_CHAIN = {
    "self-review",
    "critic-review",
    "security-review",
    "evidence",
    "capability-docs",
    "reviewer-briefing",
}

#: issue-179 (M1): the outer loop's vocabulary is EVERY node it walks except the
#: selection gate itself and the terminals. Written as a set equality in both
#: directions on purpose — a node added to the graph without a decision about
#: its skippability fails here rather than defaulting quietly either way.
#: `cleanup` (issue-186) is one of the terminals, and not skippable for the same
#: reason they are not: it is not a phase of *work* a human could decide this item
#: does not need, it is where the-loop records that it released the item's local
#: resources — and it is entered directly rather than walked into.
UNSKIPPABLE = {"phase-selection", "complete", "cleanup", "escalated"}


def test_shipped_outer_loop_marks_every_phase_but_the_gate_skippable():
    """M1, R1.1 — the widened vocabulary, pinned exactly."""
    graph = load_graph()
    every = {n.id for n in graph.ordered()}
    assert {n.id for n in graph.ordered() if n.skippable} == every - UNSKIPPABLE


def test_shipped_skip_sets_name_the_two_chains():
    """M4, R1.5 — one token per end of the walk."""
    graph = load_graph()
    assert set(graph.skip_sets["spec-chain"]) == SPEC_CHAIN
    assert set(graph.skip_sets["review-chain"]) == REVIEW_CHAIN


def test_the_selection_gate_itself_can_never_be_declared_away():
    """M2, R1.2 — the one invariant left standing (issue-179).

    With the floor gone this is what keeps "everything is selectable" from
    meaning "the harness decided": the loop starts at a node no declaration can
    reach, so a named human always answers which phases run. `required: true`
    is what enforces it — the compiler refuses `required` × `skippable`.
    """
    graph = load_graph()
    gate = graph.node("phase-selection")
    assert graph.start == "phase-selection"
    assert gate.required and not gate.skippable
    for node_id in ("complete", "escalated"):
        assert not graph.node(node_id).skippable, node_id


def test_the_former_floor_is_now_declarable_and_carries_no_required_marker():
    """M2, R1.1/R1.3 — decision-063's markers traded, on the record.

    `security-review` and `human-approval` were `required: true` ("never
    skippable, at any risk tier"). A node cannot be both, so making them
    selectable meant trading the marker — the trade decision-068 records.
    """
    graph = load_graph()
    for node_id in ("test-planning", "security-review", "human-approval"):
        node = graph.node(node_id)
        assert node.skippable and not node.required, node_id


def test_every_skippable_node_routes_forward_on_skipped():
    """M3, R1.4 — routing is authored, and it goes where the pass edge goes.

    Compilation already refuses a skippable node with no `skipped` edge; this
    pins the stronger property the edges are meant to have — skipping a node
    lands exactly where completing it would, so a declaration reorders nothing.
    """
    graph = load_graph()
    forward = {
        "phase-selection": "brainstorming",  # via `selected`, not `pass`
    }
    for node in graph.ordered():
        if not node.skippable:
            continue
        skipped = graph.next_node(node.id, "skipped")
        assert skipped is not None, node.id
        expected = (
            graph.next_node(node.id, "pass")
            or graph.next_node(node.id, "approved")
            or forward.get(node.id)
        )
        assert skipped == expected, f"{node.id}: {skipped} != {expected}"


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


def test_the_surface_defaults_to_the_work_item(selecting, repo, fake_github):
    """issue-183, owner's call on PR #184: a work item only opens a pull request
    in this repository when its author asks for one, so an untouched checklist
    leaves the outer loop on the work item."""
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    selecting.advance(WORK_ITEM, ref="github:o/r#1", event=_reply("the-loop execute"))
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.surface == "work-item"
    assert state.decisions["phase-selection"]["surface"] == "work-item"
    assert state.decisions["phase-selection"]["graph"]["surface"] == "work-item"
    # ...and the confirmation says which, so the choice is legible on the ticket.
    assert "on this work item" in fake_github.posted[-1]


def test_ticking_the_surface_row_moves_the_outer_loop_to_a_pull_request(
    selecting, repo, fake_github
):
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    selecting.advance(
        WORK_ITEM,
        ref="github:o/r#1",
        event=_reply("- [x] outer-loop-on-pull-request\nthe-loop execute"),
    )
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert state.surface == "pull-request"
    assert "on a pull request" in fake_github.posted[-1]


def test_the_surface_row_is_never_read_as_a_phase(selecting, repo, fake_github):
    """The checklist now carries two kinds of line, and a mis-parse would either
    skip a phase or flip a surface. An unticked surface row is neither a skip nor
    a refusal — it is the default."""
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    selecting.advance(
        WORK_ITEM,
        ref="github:o/r#1",
        event=_reply(
            "- [ ] outer-loop-on-pull-request\n- [ ] requirements\nthe-loop execute"
        ),
    )
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert set(state.skips) == {"requirements"}
    assert state.surface == "work-item"
    assert (
        "outer-loop-on-pull-request" not in fake_github.posted[-1].split("Refused")[-1]
    )


def test_the_posted_checklist_offers_the_surface_row(selecting, repo, fake_github):
    selecting.start(WORK_ITEM, ref="github:o/r#1")
    posted = fake_github.posted[0]
    assert "- [ ] `outer-loop-on-pull-request`" in posted
    assert "Where should the outer loop happen?" in posted


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


# -- issue-179: every phase but the gate, and what the checklist then says ------


def _fully_selectable(base):
    """The shipped shape after issue-179: nothing protected but the gate."""
    data = copy.deepcopy(base)
    for node in data["nodes"]:
        if node["id"] in ("phase-selection", "done"):
            continue
        node["skippable"] = True
        node.pop("required", None)
    data["edges"] += [
        {"from": "implementation", "to": "security-review", "on": "skipped"},
        {"from": "security-review", "to": "done", "on": "skipped"},
    ]
    return data


def test_declaring_every_phase_away_walks_the_item_to_its_terminal(repo):
    """M6, R1.8 — the widened vocabulary's end state, and it is not special.

    Nothing new in the runtime handles this: each node routes along its own
    `on: skipped` edge, and the walk ends where the edges end. What matters is
    that every node in between is *recorded* skipped rather than passed — the
    omissions are the record a reviewer reads.
    """
    runtime = Runtime(repo, graph=compile_graph(_fully_selectable(GRAPH)))
    walked = ("requirements", "approval", "tasks", "implementation", "security-review")
    _declare(repo, *walked, via="cli", token="everything")
    report = runtime.start(WORK_ITEM)

    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    assert report is not None and report.status == "pass", report
    assert state.current_node == "done"
    for node_id in walked:
        assert state.nodes[node_id].outcome == "skipped", node_id
    assert not (_spec_dir(repo) / "execution-log.md").exists(), (
        "a skipped node runs none of its hooks — no log entry, no phase label"
    )


def test_the_checklist_says_so_when_nothing_is_protected(repo, fake_github):
    """M12, R1.7 — an empty 'always runs' block is the wrong message.

    With every phase selectable, what used to be a list of protected phases
    becomes the sentence that replaces it: the honesty comes from the reply
    being signed, so the comment has to say that out loud.
    """
    runtime = Runtime(
        repo,
        graph=compile_graph(_fully_selectable(SELECT_GRAPH)),
        config={"authorizedUsers": ["@owner"]},
    )
    runtime.start(WORK_ITEM, ref="github:o/r#1")
    body = fake_github.posted[0]

    for node in ("requirements", "approval", "tasks", "implementation"):
        assert f"- [x] {node}" in body
    assert "always run and are not selectable" not in body
    assert "Every phase of this loop is selectable" in body
    assert "recorded against your name" in body


def test_the_shipped_checklist_offers_every_phase_the_item_walks(repo, fake_github):
    """M12, R1.7 — against the SHIPPED graph, not a fixture of it."""
    runtime = Runtime(repo, graph=load_graph(), config={"authorizedUsers": ["@owner"]})
    runtime.start(WORK_ITEM, ref="github:o/r#1")
    body = fake_github.posted[0]

    for node in load_graph().ordered():
        if node.skippable:
            assert f"- [x] {node.id}" in body, node.id
    assert "- [x] phase-selection" not in body
    assert "Every phase of this loop is selectable" in body
