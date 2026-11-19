"""Explainer experiments, from the checklist reply to the session prompt (issue-544).

These drive the real selection hook, the real runtime and the real prompt renderer
over a graph with the explainer skip set: a reply is classified, frozen into the
work item's state file on disk, read back as a graph context, and rendered as the
prompt block the explainer session receives. Only the GitHub transport is faked.

Feature: Opt-in explainer experiments
Requirement: docs/specs/issue-544/requirements.md R8
"""

from __future__ import annotations

import copy
import json

import pytest

from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.model import compile_graph
from the_loop.graph.runtime import Runtime
from the_loop.graph.state import STATE_FILENAME, WorkItemState
from the_loop.graphlink import GraphLink, render_graph_context

WORK_ITEM = "issue-9"
REF = "github:o/r#9"

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
        {"id": "design", "phase": "design", "skippable": True},
        {"id": "done", "terminal": True},
    ],
    "edges": [
        {"from": "phase-selection", "to": "spec-explainer", "on": "selected"},
        {"from": "spec-explainer", "to": "design", "on": "pass"},
        {"from": "spec-explainer", "to": "design", "on": "skipped"},
        {"from": "design", "to": "done", "on": "pass"},
        {"from": "design", "to": "done", "on": "skipped"},
    ],
}


class _GitHub:
    def __init__(self):
        self.posted = []

    def call(self, op, **params):
        if op == "add-comment":
            self.posted.append(str(params.get("body") or ""))
        return {"comments": []} if op == "list-comments" else {}


@pytest.fixture()
def github(monkeypatch):
    fake = _GitHub()
    monkeypatch.setattr("the_loop.graph.integrations.resolve", lambda t, c: fake)
    return fake


@pytest.fixture()
def runtime(tmp_path, github):
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    rt = Runtime(
        tmp_path,
        graph=compile_graph(copy.deepcopy(GRAPH)),
        config={"authorizedUsers": ["@owner"], "harness": "claude"},
    )
    rt.start(WORK_ITEM, ref=REF)
    return rt


def _reply(runtime, body, author="@owner"):
    runtime.advance(
        WORK_ITEM, ref=REF, event={"comments": [{"author": author, "body": body}]}
    )


def _saved(runtime):
    path = runtime.repo / "docs" / "specs" / WORK_ITEM / STATE_FILENAME
    return json.loads(path.read_text(encoding="utf-8"))


def _prompt(runtime):
    ctx = GraphLink._context_from(runtime, WORK_ITEM)
    assert ctx is not None
    return ctx, render_graph_context(ctx, WORK_ITEM)


def test_an_authorized_execute_with_slides_reaches_the_spec_explainer_prompt(
    runtime, github
):
    """
    Scenario: an authorized execute with explainer-slides ticked reaches the spec-explainer prompt
      Given the phase-selection checklist was posted with the two experiment rows
      When an authorized user replies `the-loop execute` with `explainer` and `explainer-slides` ticked
      Then `explainerExperiments: ["slides"]` is written to the work item's state file
      And the work item is at `spec-explainer`
      And the prompt block for that node names the slides experiment
    """
    checklist = github.posted[0]
    assert "- [ ] `explainer-slides`" in checklist

    _reply(
        runtime,
        "the-loop execute\n- [x] `explainer`\n- [x] `explainer-slides`\n"
        "- [ ] `explainer-flashcards`\n",
    )

    assert _saved(runtime)["explainerExperiments"] == ["slides"]
    ctx, block = _prompt(runtime)
    assert ctx.current_node == "spec-explainer"
    assert "explainer experiments chosen at phase-selection: slides" in block
    assert "flashcards" not in block


def test_an_experiment_ticked_without_the_explainer_never_reaches_a_prompt(
    runtime, github
):
    """
    Scenario: an experiment ticked without the explainer never reaches a prompt
      Given the phase-selection checklist was posted
      When an authorized user unticks `explainer` and ticks `explainer-flashcards`
      Then the explainer nodes are declared skipped
      And no `explainerExperiments` key is written
      And the confirmation says the experiment will not run, and why
      And the next node's prompt names no experiment
    """
    _reply(
        runtime,
        "the-loop execute\n- [ ] `explainer`\n- [x] `explainer-flashcards`\n",
    )

    state = WorkItemState.load(runtime.repo / "docs" / "specs" / WORK_ITEM, WORK_ITEM)
    assert "spec-explainer" in state.skips
    assert "explainerExperiments" not in _saved(runtime)
    confirmation = next(p for p in github.posted if "phase selection recorded" in p)
    assert "`explainer-flashcards`" in confirmation and "will not run" in confirmation
    ctx, block = _prompt(runtime)
    assert ctx.current_node == "design"
    assert "experiments" not in block


def test_an_unauthorized_commenters_ticked_row_is_never_frozen(runtime, github):
    """
    Scenario: an unauthorized commenter's ticked experiment row is never frozen
      Given the phase-selection checklist was posted
      When a user outside `authorizedUsers` replies `the-loop execute` with `explainer-slides` ticked
      Then the gate keeps waiting at `phase-selection`
      And no `explainerExperiments` key is written

    Requirement: docs/specs/issue-544/requirements.md, Security considerations, abuse case 1
    """
    _reply(
        runtime,
        "the-loop execute\n- [x] `explainer`\n- [x] `explainer-slides`\n",
        author="@mallory",
    )

    assert "explainerExperiments" not in _saved(runtime)
    ctx, block = _prompt(runtime)
    assert ctx.current_node == "phase-selection"
    assert "experiments" not in block
