"""The spec chain as one Claude doc (issue-536).

Feature: a work item's author chooses, at `phase-selection`, whether its spec chain
is also published as one Claude artifact (issue-471) or as one Claude doc.

The doc row sits beside the artifact row and rides the same path: read from the
authorized reply, frozen into `work-item-state.json` as `claudeDoc`, and read back
into the session prompt. At most one of the two applies: both ticked publishes
neither, and the confirmation says why.

Requirement: docs/specs/issue-536/requirements.md
"""

from __future__ import annotations

import copy
import json

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
TOKEN = "claude-doc"
ARTIFACT = "claude-artifact"

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


DOC_ONLY = f"the-loop execute\n- [ ] `{ARTIFACT}`\n- [x] `{TOKEN}`"
BOTH = f"the-loop execute\n- [x] `{ARTIFACT}`\n- [x] `{TOKEN}`"


# -- R1: the gate offers the doc beside the artifact -----------------------------


def test_the_checklist_offers_the_doc_row_ticked_by_default(repo, fake_github):
    """
    Scenario: the checklist is posted for a work item
      Given an outer loop with a phase-selection gate
      When the gate is entered
      Then the publishing section carries `claude-doc` ticked and `claude-artifact` unticked
      And says at most one may be ticked, and both ticked publishes neither
    """
    _runtime(repo).start(WORK_ITEM, ref=REF)
    posted = fake_github.posted[0]
    assert f"- [ ] `{ARTIFACT}`" in posted
    assert f"- [x] `{TOKEN}`" in posted
    assert "**Default:** a Claude doc" in posted
    assert posted.index(f"`{ARTIFACT}`") < posted.index(f"`{TOKEN}`")
    assert "Claude artifact or a Claude doc" in posted
    assert "at most one" in posted.lower()
    assert "publishes neither" in posted


def test_a_contribution_is_not_offered_the_doc_row(repo, fake_github):
    """R1.4 — a contribution owns no spec chain to publish."""
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
        WORK_ITEM, ref=REF, event=_reply(f"the-loop execute\n- [x] {TOKEN}")
    )
    state = WorkItemState.load(_spec_dir(repo), WORK_ITEM)
    assert state.claude_doc is False
    assert "Claude doc" not in _confirmation(fake_github)


@pytest.mark.parametrize("mark", ["x", " "])
def test_the_doc_row_is_never_read_as_a_phase(repo, fake_github, mark):
    """R1.5 — ticked or not, it is not a skip, an opt-in or a refusal."""
    state = _select(repo, f"the-loop execute\n- [{mark}] `{TOKEN}`", harness="claude")
    assert TOKEN not in state.skips and TOKEN not in state.opt_ins
    assert "Refused" not in _confirmation(fake_github)
    assert selection._is_non_phase(TOKEN)


# -- R2: the reply resolves one choice, against the harness ----------------------


def test_the_doc_ticked_alone_on_claude_publishes_a_doc(repo, fake_github):
    """
    Scenario: the author picks the doc on the claude harness
      Given the deployment's default harness is `claude`
      When an authorized user unticks `claude-artifact`, ticks `claude-doc` and executes
      Then `claudeDoc` is frozen true and `claudeArtifact` false
      And the confirmation says the spec chain is published as one Claude doc
    """
    state = _select(repo, DOC_ONLY, harness="claude")
    assert state.claude_doc is True
    assert state.claude_artifact is False
    decision = state.decisions["phase-selection"]
    assert decision["claudeDoc"] is True
    assert decision["graph"]["claudeDoc"] is True
    assert "one Claude doc" in _confirmation(fake_github)


def test_the_doc_with_no_known_harness_is_applied(repo, fake_github):
    """R2.2 — no CLI config seeded a harness; the session's own guard decides."""
    assert _select(repo, DOC_ONLY).claude_doc is True


def test_the_doc_on_another_harness_is_not_applied(repo, fake_github):
    """
    Scenario: the author picks the doc but the item runs on codex
      Given the reply also picks the `codex` harness
      When it is executed
      Then `claudeDoc` is frozen false
      And the confirmation names `claude-doc` as not applied on `codex`
    """
    state = _select(
        repo,
        DOC_ONLY + "\n- [x] `harness-codex`",
        harness="claude",
        offeredHarnesses=["claude", "codex"],
    )
    assert state.harness == "codex"
    assert state.claude_doc is False
    confirmation = _confirmation(fake_github)
    assert f"Not applied: `{TOKEN}`" in confirmation
    assert "`codex`" in confirmation


def test_both_ticked_publishes_neither(repo, fake_github):
    """
    Scenario: the author ticks both rows
      Given an outer loop on the claude harness
      When an authorized user ticks `claude-artifact` and `claude-doc` and executes
      Then neither `claudeArtifact` nor `claudeDoc` is frozen true
      And the confirmation says two rows were ticked and the files stay markdown only
    """
    state = _select(repo, BOTH, harness="claude")
    assert state.claude_doc is False
    assert state.claude_artifact is False
    confirmation = _confirmation(fake_github)
    assert f"`{ARTIFACT}` and `{TOKEN}` were both ticked" in confirmation
    assert "markdown files only" in confirmation


def test_the_artifact_picked_alone_is_unchanged(repo, fake_github):
    """The issue-471 behaviour stands when the author picks the artifact."""
    state = _select(
        repo, f"the-loop execute\n- [x] `{ARTIFACT}`\n- [ ] `{TOKEN}`", harness="claude"
    )
    assert state.claude_artifact is True
    assert state.claude_doc is False
    assert "one Claude artifact" in _confirmation(fake_github)


@pytest.mark.parametrize(
    "body", [f"the-loop execute\n- [ ] `{TOKEN}`", "the-loop execute"]
)
def test_unticked_or_absent_is_not_a_doc(repo, fake_github, body):
    """R2.5 — fail closed."""
    state = _select(repo, body, harness="claude")
    assert state.claude_doc is False
    assert "markdown files only" in _confirmation(fake_github)


def test_an_unauthorized_tick_changes_nothing(repo, fake_github):
    """Abuse case: only an authorized `the-loop execute` makes a tick count."""
    runtime = _runtime(repo, harness="claude")
    runtime.start(WORK_ITEM, ref=REF)
    runtime.advance(WORK_ITEM, ref=REF, event=_reply(DOC_ONLY, author="@mallory"))
    state = WorkItemState.load(_spec_dir(repo), WORK_ITEM)
    assert state.claude_doc is False
    assert state.current_node == "phase-selection"


# -- R3: the frozen record -------------------------------------------------------


def test_the_state_round_trips(repo):
    state = WorkItemState(work_item=WORK_ITEM, claude_doc=True)
    state.save(_spec_dir(repo))
    data = json.loads((_spec_dir(repo) / "work-item-state.json").read_text())
    assert data["claudeDoc"] is True
    assert WorkItemState.load(_spec_dir(repo), WORK_ITEM).claude_doc is True


@pytest.mark.parametrize("value", [None, "true", 1, ["x"], {"a": 1}, False])
def test_anything_but_the_boolean_true_reads_as_false(repo, value):
    """R3.2 and the abuse case: the state file is agent-writable."""
    path = _spec_dir(repo) / "work-item-state.json"
    data = {"workItem": WORK_ITEM}
    if value is not None:
        data["claudeDoc"] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    assert WorkItemState.load(_spec_dir(repo), WORK_ITEM).claude_doc is False


def test_both_true_on_disk_keeps_the_artifact(repo):
    """R3.3 — the invariant holds on a hand-edited file too."""
    path = _spec_dir(repo) / "work-item-state.json"
    path.write_text(
        json.dumps({"workItem": WORK_ITEM, "claudeArtifact": True, "claudeDoc": True}),
        encoding="utf-8",
    )
    state = WorkItemState.load(_spec_dir(repo), WORK_ITEM)
    assert (state.claude_artifact, state.claude_doc) == (True, False)


def test_the_attribute_catalogue_lists_the_key():
    """R3.5 — `test_state_portability.py` pins the catalogue to `as_dict`."""
    from the_loop.state import ATTRIBUTES

    assert "claudeDoc" in {a.key for a in ATTRIBUTES}


def test_the_archive_records_and_summarises_the_doc(tmp_path):
    """R3.4 — the terminal record carries it, and `graph` lists it as a choice."""
    from the_loop import archive
    from the_loop.commands.graph_cmd import _archived_lines
    from the_loop.graph.bootstrap import build_runtime

    spec = tmp_path / "docs" / "specs" / "issue-3"
    spec.mkdir(parents=True)
    (spec / "work-item-state.json").write_text(
        json.dumps(
            {"workItem": "issue-3", "currentNode": "", "nodes": {}, "claudeDoc": True}
        )
    )
    runtime = build_runtime(tmp_path, spec_root="docs/specs", origin_repo="octo/repo")
    record = archive.terminal_record(runtime, "issue-3")
    assert record is not None
    assert record["selections"]["claudeDoc"] is True
    lines = _archived_lines(
        {
            "workItem": "issue-3",
            "archived": {"outcome": "completed", "terminal": record},
        }
    )
    assert any(line.startswith("  choices:") and "claude-doc" in line for line in lines)


# -- R4: the session is told -----------------------------------------------------


def _ctx(loop=PDLC_WORK_ITEM_LOOP, claude_doc=True):
    return GraphContext(
        current_node="requirements",
        phase="requirements-definition",
        status="in-progress",
        reason="",
        messages=(),
        next_command="new-requirement",
        actor="agent",
        loop=loop,
        claude_doc=claude_doc,
    )


def test_the_outer_loop_prompt_tells_the_session_to_publish_a_doc():
    """R4.1"""
    block = render_graph_context(_ctx(), WORK_ITEM)
    assert "publish the spec chain as ONE Claude doc" in block
    assert "never a gate answer" in block
    assert "read a tab before rewriting it" in block
    assert "Claude artifact" not in block


@pytest.mark.parametrize(
    "ctx, pr",
    [
        (_ctx(claude_doc=False), None),
        (_ctx(), 7),
        (_ctx(loop=PDLC_CONTRIBUTION_LOOP), None),
        (_ctx(loop=PDLC_ADHOC_LOOP), None),
        (_ctx(loop=PDLC_REVIEW_LOOP), None),
    ],
)
def test_no_other_prompt_carries_the_doc_line(ctx, pr):
    """R4.2"""
    assert "Claude doc" not in render_graph_context(ctx, WORK_ITEM, pr_number=pr)


def test_the_prompt_reads_the_frozen_state(repo, fake_github):
    """The context a session prompt is rendered from carries the frozen value."""
    from the_loop.graphlink import GraphLink

    runtime = _runtime(repo, harness="claude")
    runtime.start(WORK_ITEM, ref=REF)
    runtime.advance(WORK_ITEM, ref=REF, event=_reply(DOC_ONLY))
    ctx = GraphLink._context_from(runtime, WORK_ITEM)
    assert ctx is not None and ctx.claude_doc is True
