"""The spec chain as one Claude artifact (issue-471).

Feature: a work item's author chooses, at `phase-selection`, whether its spec chain
is also published as one Claude artifact.

The choice rides the path every per-work-item choice already rides: one row on the
checklist, read from the authorized reply, frozen into `work-item-state.json`, and
read back into the session prompt. It applies only on the `claude` harness; a tick on
any other harness is not applied, and the confirmation says so.
"""

from __future__ import annotations

import copy

import pytest

from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.hooks import selection
from the_loop.graph.model import (
    PDLC_ADHOC_LOOP,
    PDLC_CONTRIBUTION_LOOP,
    PDLC_REVIEW_LOOP,
    PDLC_WORK_ITEM_LOOP,
    compile_graph,
    load_graph,
)
from the_loop.graph.runtime import Runtime
from the_loop.graph.state import WorkItemState
from the_loop.graphlink import GraphContext, render_graph_context

WORK_ITEM = "issue-1"
REF = "github:o/r#1"
TOKEN = "claude-artifact"

#: The smallest outer loop with a selection gate: one selectable phase after it.
GRAPH = {
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
        {"id": "requirements", "phase": "requirements-definition", "skippable": True},
        {"id": "done", "terminal": True},
    ],
    "edges": [
        {"from": "phase-selection", "to": "requirements", "on": "selected"},
        {"from": "requirements", "to": "done", "on": "pass"},
        {"from": "requirements", "to": "done", "on": "skipped"},
    ],
}


class _FakeGitHub:
    """Serves the ticket's comments and records what the-loop posts."""

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


def _runtime(repo, graph=None, **config):
    return Runtime(
        repo,
        graph=graph or compile_graph(copy.deepcopy(GRAPH)),
        config={"authorizedUsers": ["@owner"], **config},
    )


def _reply(body, author="@owner"):
    return {"comments": [{"author": author, "body": body}]}


def _select(repo, body, **config):
    runtime = _runtime(repo, **config)
    runtime.start(WORK_ITEM, ref=REF)
    runtime.advance(WORK_ITEM, ref=REF, event=_reply(body))
    return WorkItemState.load(_spec_dir(repo), WORK_ITEM)


def _confirmation(fake_github):
    return next(p for p in fake_github.posted if "phase selection recorded" in p)


# -- R1: the gate offers the choice --------------------------------------------


def test_the_outer_loop_checklist_offers_an_unticked_row(repo, fake_github):
    """
    Scenario: the checklist is posted for a work item
      Given an outer loop with a phase-selection gate
      When the gate is entered
      Then the checklist carries an unticked `claude-artifact` row
      And says it applies only on the `claude` harness
    """
    _runtime(repo).start(WORK_ITEM, ref=REF)
    posted = fake_github.posted[0]
    assert f"- [ ] `{TOKEN}`" in posted
    assert "Publish the spec chain as a Claude artifact too?" in posted
    assert "the-loop ignores this box" in posted


def test_a_contribution_is_not_offered_the_row(repo, fake_github):
    """R1.3 — a contribution owns no spec chain to publish."""
    fake_github.comments = [
        {
            "user": {"login": "owner"},
            "body": "the-loop contribute\nGoal: fix it\nSuccess criteria:\n- it works\n",
        }
    ]
    runtime = _runtime(repo, graph=load_graph(name=PDLC_CONTRIBUTION_LOOP))
    runtime.start(WORK_ITEM, ref=REF)
    runtime.advance(WORK_ITEM, ref=REF)
    checklist = next(p for p in fake_github.posted if selection.SELECTION_MARKER in p)
    assert TOKEN not in checklist
    runtime.advance(
        WORK_ITEM, ref=REF, event=_reply(f"- [x] {TOKEN}\nthe-loop execute")
    )
    state = WorkItemState.load(_spec_dir(repo), WORK_ITEM)
    assert state.claude_artifact is False
    assert "Claude artifact" not in _confirmation(fake_github)


@pytest.mark.parametrize("mark", ["x", " "])
def test_the_row_is_never_read_as_a_phase(repo, fake_github, mark):
    """R1.4 — ticked or not, it is not a skip, an opt-in or a refusal."""
    state = _select(repo, f"- [{mark}] `{TOKEN}`\nthe-loop execute", harness="claude")
    assert TOKEN not in state.skips and TOKEN not in state.opt_ins
    assert "Refused" not in _confirmation(fake_github)
    assert selection._is_non_phase(TOKEN)


# -- R2: the reply resolves it, against the harness ----------------------------


def test_ticked_on_the_claude_harness_publishes(repo, fake_github):
    """
    Scenario: the author asks for the artifact on the claude harness
      Given the deployment's default harness is `claude`
      When an authorized user ticks `claude-artifact` and replies `the-loop execute`
      Then `claudeArtifact` is frozen true
      And the confirmation says the spec chain is published as one Claude artifact
    """
    state = _select(repo, f"- [x] `{TOKEN}`\nthe-loop execute", harness="claude")
    assert state.claude_artifact is True
    decision = state.decisions["phase-selection"]
    assert decision["claudeArtifact"] is True
    assert decision["graph"]["claudeArtifact"] is True
    assert "one Claude artifact" in _confirmation(fake_github)


def test_ticked_on_another_harness_is_not_applied(repo, fake_github):
    """
    Scenario: the author asks for the artifact but the item runs on codex
      Given the reply also picks the `codex` harness
      When it is executed
      Then `claudeArtifact` is frozen false
      And the confirmation names `codex` as the harness it was not applied on
    """
    state = _select(
        repo,
        f"- [x] `{TOKEN}`\n- [x] `harness-codex`\nthe-loop execute",
        harness="claude",
        offeredHarnesses=["claude", "codex"],
    )
    assert state.harness == "codex"
    assert state.claude_artifact is False
    confirmation = _confirmation(fake_github)
    assert f"Not applied: `{TOKEN}`" in confirmation
    assert "`codex`" in confirmation


def test_ticked_on_a_non_claude_default_is_not_applied(repo, fake_github):
    state = _select(repo, f"- [x] `{TOKEN}`\nthe-loop execute", harness="codex")
    assert state.claude_artifact is False
    assert f"Not applied: `{TOKEN}`" in _confirmation(fake_github)


def test_ticked_with_no_known_harness_is_applied(repo, fake_github):
    """R2.2 — no CLI config seeded a harness; the session's own guard decides."""
    state = _select(repo, f"- [x] `{TOKEN}`\nthe-loop execute")
    assert state.claude_artifact is True


@pytest.mark.parametrize(
    "body", [f"- [ ] `{TOKEN}`\nthe-loop execute", "the-loop execute"]
)
def test_unticked_or_absent_is_markdown_only(repo, fake_github, body):
    """R2.4, R2.5 — fail closed, and named in the confirmation."""
    state = _select(repo, body, harness="claude")
    assert state.claude_artifact is False
    assert "markdown files only" in _confirmation(fake_github)


# -- R3: the frozen record -----------------------------------------------------


def test_the_state_round_trips(repo):
    state = WorkItemState(work_item=WORK_ITEM, claude_artifact=True)
    state.save(_spec_dir(repo))
    assert WorkItemState.load(_spec_dir(repo), WORK_ITEM).claude_artifact is True


@pytest.mark.parametrize("value", [None, "true", 1, ["x"], {"a": 1}, False])
def test_anything_but_the_boolean_true_reads_as_false(repo, value):
    """R3.2 and the abuse case: the state file is agent-writable."""
    import json

    path = _spec_dir(repo) / "work-item-state.json"
    data = {"workItem": WORK_ITEM}
    if value is not None:
        data["claudeArtifact"] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    assert WorkItemState.load(_spec_dir(repo), WORK_ITEM).claude_artifact is False


def test_the_attribute_catalogue_lists_the_key():
    """`test_state_portability.py` pins the catalogue to `as_dict`; this names
    the key so the pin's failure, if any, points here."""
    from the_loop.state import ATTRIBUTES

    assert "claudeArtifact" in {a.key for a in ATTRIBUTES}


# -- R4: the session is told ---------------------------------------------------


def _ctx(loop=PDLC_WORK_ITEM_LOOP, claude_artifact=True):
    return GraphContext(
        current_node="requirements",
        phase="requirements-definition",
        status="in-progress",
        reason="",
        messages=(),
        next_command="new-requirement",
        actor="agent",
        loop=loop,
        claude_artifact=claude_artifact,
    )


def test_the_outer_loop_prompt_tells_the_session_to_publish():
    """R4.1"""
    block = render_graph_context(_ctx(), WORK_ITEM)
    assert "publish the spec chain as ONE Claude artifact" in block
    assert "never a gate answer" in block


@pytest.mark.parametrize(
    "ctx, pr",
    [
        (_ctx(claude_artifact=False), None),
        (_ctx(), 7),
        (_ctx(loop=PDLC_CONTRIBUTION_LOOP), None),
        (_ctx(loop=PDLC_ADHOC_LOOP), None),
        (_ctx(loop=PDLC_REVIEW_LOOP), None),
    ],
)
def test_no_other_prompt_carries_the_line(ctx, pr):
    """R4.2"""
    assert "Claude artifact" not in render_graph_context(ctx, WORK_ITEM, pr_number=pr)


def test_the_prompt_reads_the_frozen_state(repo, fake_github):
    """The context a session prompt is rendered from carries the frozen value."""
    from the_loop.graphlink import GraphLink

    runtime = _runtime(repo, harness="claude")
    runtime.start(WORK_ITEM, ref=REF)
    runtime.advance(
        WORK_ITEM, ref=REF, event=_reply(f"- [x] `{TOKEN}`\nthe-loop execute")
    )
    ctx = GraphLink._context_from(runtime, WORK_ITEM)
    assert ctx is not None and ctx.claude_artifact is True
