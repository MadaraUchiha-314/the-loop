"""Opt-in explainer experiments: slides and flashcards (issue-544, R8).

Feature: the explainer section of the phase-selection checklist offers two
experiment rows, `explainer-slides` and `explainer-flashcards`, unticked. A
ticked row rides the claude-doc path: read from the authorized reply, frozen
into `work-item-state.json` as `explainerExperiments`, and read back into the
prompt of the two explainer nodes only. An experiment needs `explainer` itself.

Requirement: docs/specs/issue-544/requirements.md
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from the_loop.channels import slack
from the_loop.channels.slack import selection_rows
from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks import selection, sideeffects
from the_loop.graph.model import PDLC_WORK_ITEM_LOOP, compile_graph, load_graph
from the_loop.graph.runtime import Runtime
from the_loop.graph.state import WorkItemState
from the_loop.graphlink import GraphContext, GraphLink, render_graph_context

WORK_ITEM = "issue-1"
REF = "github:o/r#1"
SLIDES = "explainer-slides"
CARDS = "explainer-flashcards"

#: The smallest outer loop with a selection gate and an explainer skip set.
GRAPH = {
    "start": "phase-selection",
    "skipSets": {"explainer": ["spec-explainer"]},
    "nodes": [
        {
            "id": "phase-selection",
            "phase": "phase-selection",
            "actor": "human",
            "required": True,
            "entry": ["post-phase-selection"],
            "exit": ["classify-phase-selection"],
        },
        {"id": "spec-explainer", "phase": "spec-explainer", "skippable": True},
        {"id": "done", "terminal": True},
    ],
    "edges": [
        {"from": "phase-selection", "to": "spec-explainer", "on": "selected"},
        {"from": "spec-explainer", "to": "done", "on": "pass"},
        {"from": "spec-explainer", "to": "done", "on": "skipped"},
    ],
}


class _FakeGitHub:
    def __init__(self):
        self.comments = []
        self.posted = []

    def call(self, op, **params):
        if op == "list-comments":
            return {"comments": list(self.comments)}
        if op == "add-comment":
            self.posted.append(str(params.get("body") or ""))
        return {}


@pytest.fixture()
def fake_github(monkeypatch):
    provider = _FakeGitHub()
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve", lambda target, config: provider
    )
    return provider


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    return tmp_path


def _spec_dir(repo):
    return repo / "docs" / "specs" / WORK_ITEM


def _runtime(repo):
    return Runtime(
        repo,
        graph=compile_graph(copy.deepcopy(GRAPH)),
        config={"authorizedUsers": ["@owner"], "harness": "claude"},
    )


def _select(repo, body, author="@owner"):
    runtime = _runtime(repo)
    runtime.start(WORK_ITEM, ref=REF)
    runtime.advance(
        WORK_ITEM, ref=REF, event={"comments": [{"author": author, "body": body}]}
    )
    return runtime, WorkItemState.load(_spec_dir(repo), WORK_ITEM)


def _confirmation(fake_github):
    return next(p for p in fake_github.posted if "phase selection recorded" in p)


def _reply(explainer="x", slides=" ", cards=" "):
    return (
        "the-loop execute\n"
        f"- [{explainer}] `explainer`\n"
        f"- [{slides}] `{SLIDES}`\n"
        f"- [{cards}] `{CARDS}`\n"
    )


# -- R8 AC 1: the rows ----------------------------------------------------------


def test_rows_render_unticked_in_explainer_section(repo, fake_github):
    """
    Scenario: the checklist is posted for a work item with an explainer
      Given an outer loop whose graph has the explainer skip set
      When the gate is entered
      Then the explainer section carries both experiment rows, unticked
      And they follow the `explainer` row
    """
    _runtime(repo).start(WORK_ITEM, ref=REF)
    posted = fake_github.posted[0]
    assert f"- [ ] `{SLIDES}`" in posted
    assert f"- [ ] `{CARDS}`" in posted
    assert (
        posted.index("- [x] `explainer`")
        < posted.index(f"`{SLIDES}`")
        < posted.index(f"`{CARDS}`")
    )
    assert "need `explainer` ticked" in posted


def test_no_explainer_skip_set_means_no_experiment_rows(repo, fake_github):
    graph = copy.deepcopy(GRAPH)
    del graph["skipSets"]
    Runtime(
        repo, graph=compile_graph(graph), config={"authorizedUsers": ["@owner"]}
    ).start(WORK_ITEM, ref=REF)
    assert SLIDES not in fake_github.posted[0]


# -- R8 AC 2, 5, 6: parse, validate, freeze --------------------------------------


def test_a_ticked_row_freezes_the_experiment(repo, fake_github):
    _, state = _select(repo, _reply(slides="x"))
    assert state.explainer_experiments == ["slides"]
    assert state.decisions["phase-selection"]["explainerExperiments"] == ["slides"]
    assert "slides" in _confirmation(fake_github)
    saved = json.loads((_spec_dir(repo) / "work-item-state.json").read_text())
    assert saved["explainerExperiments"] == ["slides"]


def test_both_rows_freeze_in_a_fixed_order(repo, fake_github):
    _, state = _select(repo, _reply(slides="x", cards="x"))
    assert state.explainer_experiments == ["slides", "flashcards"]


def test_an_experiment_without_the_explainer_is_dropped_and_explained(
    repo, fake_github
):
    _, state = _select(repo, _reply(explainer=" ", slides="x"))
    assert state.explainer_experiments == []
    text = _confirmation(fake_github)
    assert "will not run" in text and "`explainer`" in text


@pytest.mark.parametrize(
    "body",
    [
        _reply(),
        "the-loop execute\n",
        "the-loop execute\n- [?] `explainer-slides`\n",
        "the-loop execute\n- [x] `explainer-reels`\n",
    ],
)
def test_unticked_absent_unreadable_or_unknown_rows_mean_off(repo, fake_github, body):
    _, state = _select(repo, body)
    assert state.explainer_experiments == []
    saved = json.loads((_spec_dir(repo) / "work-item-state.json").read_text())
    assert "explainerExperiments" not in saved
    assert "explainer-reels" not in state.skips


@pytest.mark.parametrize("token", [SLIDES, CARDS, "explainer-reels"])
def test_experiment_tokens_are_never_phases(token):
    assert selection._is_non_phase(token)


def test_state_without_the_key_loads_unchanged(tmp_path):
    (tmp_path / "work-item-state.json").write_text(
        json.dumps({"workItem": WORK_ITEM, "currentNode": "design"})
    )
    state = WorkItemState.load(tmp_path, WORK_ITEM)
    assert state.explainer_experiments == []
    assert "explainerExperiments" not in state.as_dict()


def test_a_hand_edited_unknown_value_is_dropped_on_load(tmp_path):
    (tmp_path / "work-item-state.json").write_text(
        json.dumps(
            {
                "workItem": WORK_ITEM,
                "explainerExperiments": ["slides", "<script>", 3, "slides"],
            }
        )
    )
    assert WorkItemState.load(tmp_path, WORK_ITEM).explainer_experiments == ["slides"]


# -- R8 AC 3-4: the prompt line ---------------------------------------------------


def _ctx(node, experiments=("slides", "flashcards"), loop=PDLC_WORK_ITEM_LOOP):
    return GraphContext(
        current_node=node,
        phase=node,
        status="in-progress",
        reason="",
        messages=(),
        next_command="explain",
        actor="agent",
        loop=loop,
        explainer_experiments=tuple(experiments),
    )


@pytest.mark.parametrize("node", ["spec-explainer", "code-explainer"])
def test_the_explainer_nodes_name_the_experiments(node):
    block = render_graph_context(_ctx(node), WORK_ITEM)
    assert "slides, flashcards" in block
    assert "experiments chosen at phase-selection" in block


@pytest.mark.parametrize(
    "ctx",
    [
        _ctx("design"),
        _ctx("spec-quiz"),
        _ctx("spec-explainer", experiments=()),
    ],
)
def test_no_other_prompt_carries_the_experiments_line(ctx):
    assert "experiments chosen" not in render_graph_context(ctx, WORK_ITEM)


def test_the_prompt_reads_the_frozen_state(repo, fake_github):
    runtime, _ = _select(repo, _reply(cards="x"))
    ctx = GraphLink._context_from(runtime, WORK_ITEM)
    assert ctx is not None and ctx.explainer_experiments == ("flashcards",)


def test_the_archived_summary_lists_the_experiments_under_choices():
    from the_loop.commands.graph_cmd import _archived_lines

    lines = _archived_lines(
        {
            "workItem": WORK_ITEM,
            "archived": {
                "terminal": {"selections": {"explainerExperiments": ["slides"]}}
            },
        }
    )
    assert any("explainer-slides" in line for line in lines)


# -- R8 AC 7: Slack ----------------------------------------------------------------


def test_slack_reads_every_explainer_row_as_a_setting(repo, fake_github):
    _runtime(repo).start(WORK_ITEM, ref=REF)
    rows = selection_rows(fake_github.posted[0])
    assert rows is not None
    tokens = [r.token for r in rows.others]
    assert SLIDES in tokens and CARDS in tokens
    assert all(r.token != SLIDES for r in rows.phases)
    assert slack._is_setting_token("explainer-anything")


# -- R3 AC 9: the design-approval focus line -----------------------------------------


class _Recorder:
    def __init__(self):
        self.bodies = []

    def call(self, op, **params):
        self.bodies.append(params.get("body", ""))
        return {}


def _request(monkeypatch, node, params):
    recorder = _Recorder()
    monkeypatch.setattr(sideeffects, "_integration", lambda ctx: recorder)
    ctx = HookContext(
        work_item=WorkItem(ref=REF, id=WORK_ITEM, spec_dir=Path(".")),
        node={"id": node},
        boundary="entry",
        repo=Path("."),
        params=params,
    )
    sideeffects.request_review(ctx)
    return recorder.bodies[0]


def test_the_design_approval_request_carries_the_focus_line(monkeypatch):
    body = _request(monkeypatch, "design-approval", {"focus": "design-approval"})
    assert "Start with `design.md` § Interfaces" in body


def test_other_gates_post_todays_message(monkeypatch):
    plain = _request(monkeypatch, "requirements-approval", {})
    assert "Start with" not in plain
    unknown = _request(monkeypatch, "requirements-approval", {"focus": "nope"})
    assert unknown == plain


def test_the_shipped_graph_sets_the_focus_on_design_approval_only():
    graph = load_graph()
    focused = [
        node.id
        for node in graph.ordered()
        for entry in node.entry
        if isinstance(entry, dict)
        and entry.get("hook") == "request-review"
        and (entry.get("with") or {}).get("focus")
    ]
    assert focused == ["design-approval"]


# -- R8 AC 3-4, abuse case 2: the explainer template's experiment tabs --------------

TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "the-loop"
    / "templates"
    / "explainer.html"
)


@pytest.mark.skipif(not TEMPLATE.is_file(), reason="plugin skills not present")
def test_the_template_carries_the_experiment_tabs_and_their_data_blocks():
    text = TEMPLATE.read_text(encoding="utf-8")
    for needle in (
        'id="tab-slides"',
        'id="tab-cards"',
        'data-slides="slides"',
        'data-cards="cards"',
        '<script type="application/json" id="slides">',
        '<script type="application/json" id="cards">',
        "aria-pressed",
        "aria-live",
    ):
        assert needle in text, needle


@pytest.mark.skipif(not TEMPLATE.is_file(), reason="plugin skills not present")
def test_the_template_engine_never_assigns_markup():
    """Abuse case 2: spec and diff text in a data block renders as text only."""
    text = TEMPLATE.read_text(encoding="utf-8")
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert sink not in text, sink


# -- R3 AC 8, NFR backward compatibility: old and new designs both pass the gate ----

REPO = Path(__file__).resolve().parents[2]


def _design_gate_sections():
    graph = load_graph()
    for entry in graph.nodes["design"].exit:
        if isinstance(entry, dict) and entry.get("hook") == "validate-artifacts":
            wanted = (entry.get("with") or {}).get("sections")
            if wanted:
                return list(wanted)
    raise AssertionError("the design node declares no gated sections")


@pytest.mark.parametrize(
    "path",
    [
        REPO / "docs" / "specs" / "issue-538" / "design.md",  # the old shape
        REPO / "docs" / "specs" / "issue-544" / "design.md",  # the new shape, filled
        REPO / "skills" / "the-loop" / "templates" / "design.md",  # the new template
    ],
    ids=["old-shape", "new-shape", "new-template"],
)
def test_the_design_gate_sections_validate_on_old_and_new_designs(path):
    from the_loop.graph.frontmatter import sections, split_front_matter

    if not path.is_file():
        pytest.skip(f"{path} not present")
    _, body = split_front_matter(path.read_text(encoding="utf-8"))
    found = {heading.strip(): text for heading, text in sections(body).items()}
    for wanted in _design_gate_sections():
        assert wanted in found, f"{path.name}: missing {wanted}"
        assert found[wanted].strip(), f"{path.name}: empty {wanted}"
