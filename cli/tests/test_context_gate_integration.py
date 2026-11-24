"""The opt-in context pair: gather the current state, then wait for its author
(issue-553).

Walked on the SHIPPED outer loop with real hook chains over a temporary spec
directory, beside ``test_brainstorm_gate_integration.py`` whose hooks the pair
reuses. What is new here is the default: both nodes are ``optIn``, so each test
says which rows the work item ticked, and the first thing proved is that an item
ticking neither walks exactly as it did before the nodes existed.

Requirement: docs/specs/issue-553/requirements.md R1, R2.7, R2.8, R3, and abuse
cases 3-6 of its Security considerations.
"""

from __future__ import annotations

import json

import pytest

from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.frontmatter import read_front_matter
from the_loop.graph.model import PHASE_VOCABULARY, load_graph
from the_loop.graph.runtime import Runtime
from the_loop.graph.state import WorkItemState

WORK_ITEM = "issue-1"
GATHER, GATE = "context-gathering", "context-approval"

CURRENT_STATE = (
    "---\ntype: current-state\nphase: context-gathering\nstatus: draft\n"
    "approvedBy: []\ngatheredAt: 0123abc\n---\n\n# Current state: x\n\n"
    "## Scope\n\nThe checklist.\n\n## How it works today\n\nIt renders rows.\n\n"
    "## Questions and answers\n\n- **Q:** which rows?\n"
)
BRAINSTORM = (
    "---\ntype: brainstorm\nphase: brainstorming\nstatus: draft\napprovedBy: []\n"
    "---\n\n# Brainstorm: x\n\n## Problem / opportunity\n\nreal\n\n"
    "## Open questions\n\nnone\n"
)


class _FakeGitHub:
    def __init__(self):
        self.posted = []
        self.calls = []

    def call(self, op, **params):
        self.calls.append((op, params))
        if op == "add-comment":
            self.posted.append(str(params.get("body") or ""))
        if op == "list-comments":
            return {"comments": []}
        return {}


@pytest.fixture()
def github(monkeypatch):
    provider = _FakeGitHub()
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve", lambda target, config: provider
    )
    return provider


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    return tmp_path


def _spec(repo):
    return repo / "docs" / "specs" / WORK_ITEM


def _selected(repo, *ticked, extra=None):
    """A work item whose phase selection was just answered, with the opt-in
    rows in ``ticked`` selected — the pointer still on `phase-selection`."""
    state = {
        "workItem": WORK_ITEM,
        "currentNode": "phase-selection",
        "decisions": {"phase-selection": {"at": "2026-11-24T00:00:00Z"}},
        "skips": {},
        "optIns": {
            node: {"via": "selection", "token": node, "by": "@owner"} for node in ticked
        },
    }
    state.update(extra or {})
    (_spec(repo) / "work-item-state.json").write_text(json.dumps(state))


def _runtime(repo):
    return Runtime(repo, graph=load_graph(), config={"authorizedUsers": ["owner"]})


def _reply(*bodies, author="owner"):
    return {"comments": [{"author": author, "body": b} for b in bodies]}


def _state(repo):
    return WorkItemState.load(_spec(repo), WORK_ITEM)


def _node(repo):
    return _state(repo).current_node


def _write(repo, text=CURRENT_STATE):
    (_spec(repo) / "current-state.md").write_text(text)


def _status(repo):
    return read_front_matter(_spec(repo) / "current-state.md")["status"]


def _parked_at_the_gate(repo):
    """Both rows ticked, the file written, the gate entered."""
    _selected(repo, GATHER, GATE)
    runtime = _runtime(repo)
    runtime.advance(WORK_ITEM)
    assert _node(repo) == GATHER
    _write(repo)
    runtime.advance(WORK_ITEM)
    assert _node(repo) == GATE
    return runtime


# -- the graph's shape (T1) -------------------------------------------------------


def test_the_pair_is_declared_opt_in_between_the_import_and_the_brainstorm():
    """
    Feature: a context-gathering phase before the spec chain
    Scenario: the graph's shape, pinned
      Given the shipped outer loop
      Then context-gathering and context-approval sit between import-handoff
        and brainstorming, both opt-in, each with a checklist description
      And context-gathering is an agent node with a phase of its own that
        produces current-state.md through /the-loop:gather-context
      And context-approval is a human node in the same phase, with no pass edge
      And neither is in the spec-chain skip set
    Requirement: docs/specs/issue-553/requirements.md R1.1, R1.2, R1.7, R1.8, R1.10
    """
    graph = load_graph()
    order = [n.id for n in graph.ordered()]
    at = order.index("import-handoff")
    assert order[at : at + 4] == ["import-handoff", GATHER, GATE, "brainstorming"]

    gather, gate = graph.node(GATHER), graph.node(GATE)
    for node in (gather, gate):
        assert node.opt_in and node.skippable and node.description
    assert gather.actor == "agent" and gather.phase == "context-gathering"
    assert gather.produces == ("current-state.md",)
    assert gather.command == "gather-context"
    # The gate carries the phase too, so a handoff that enters at it is labelled.
    assert gate.actor == "human" and gate.phase == "context-gathering"

    assert graph.next_node(GATHER, "pass") == GATE
    for outcome in ("not-entered", "skipped"):
        assert graph.next_node(GATHER, outcome) == "brainstorming"
    for outcome in ("approved", "approved-with-comments", "skipped"):
        assert graph.next_node(GATE, outcome) == "brainstorming"
    assert graph.next_node(GATE, "changes-requested") == GATHER
    assert graph.next_node(GATE, "pass") is None

    assert not {GATHER, GATE} & set(graph.skip_sets["spec-chain"])
    at = PHASE_VOCABULARY.index("phase-selection")
    assert PHASE_VOCABULARY[at + 1] == "context-gathering"


# -- every tick combination (T3 a-c, h, i) ----------------------------------------


def test_ticking_neither_row_walks_as_before(repo, github):
    """
    Feature: a context-gathering phase before the spec chain
    Scenario: A work item that ticks neither row walks as before
      Given a work item whose phase selection ticked neither context row
      When the walk leaves phase selection
      Then it reaches brainstorming without entering either context node
      And no review was requested and no context label was applied
      And a current-state.md left in the folder changes none of that
    Requirement: docs/specs/issue-553/requirements.md R1.3
    """
    _selected(repo)
    _write(repo)
    report = _runtime(repo).advance(WORK_ITEM)
    assert report.status == "pass"
    state = _state(repo)
    assert state.current_node == "brainstorming"
    assert state.nodes[GATHER].outcome == "skipped"
    assert GATE not in state.nodes
    assert not any(GATE in body for body in github.posted)
    assert "loop:context-gathering" not in json.dumps(github.calls, default=str)
    assert _status(repo) == "draft"


def test_gathering_ticked_alone_does_not_hold_the_work_item(repo, github):
    """
    Feature: a context-gathering phase before the spec chain
    Scenario: A context node ticked alone does not hold the work item
      Given a work item that ticked context-gathering and not context-approval
      When the session writes current-state.md and completes the node
      Then the walk reaches brainstorming with no human stop
      And current-state.md is not locked, because no gate approved it
    Requirement: docs/specs/issue-553/requirements.md R1.4
    """
    _selected(repo, GATHER)
    runtime = _runtime(repo)
    runtime.advance(WORK_ITEM)
    assert _node(repo) == GATHER
    _write(repo)
    report = runtime.advance(WORK_ITEM)
    assert report.outcome == "pass"
    state = _state(repo)
    assert state.current_node == "brainstorming"
    assert state.nodes[GATE].outcome == "skipped"
    assert not any(GATE in body for body in github.posted)
    assert _status(repo) == "draft"


def test_the_gate_ticked_alone_has_nothing_to_approve(repo, github):
    """
    Feature: a context-gathering phase before the spec chain
    Scenario: A context node ticked alone does not hold the work item
      Given a work item that ticked context-approval and not context-gathering
      When the walk leaves phase selection
      Then it routes past the gate to brainstorming
    Requirement: docs/specs/issue-553/requirements.md R1.5
    """
    _selected(repo, GATE)
    _runtime(repo).advance(WORK_ITEM)
    state = _state(repo)
    assert state.current_node == "brainstorming"
    assert GATE not in state.nodes or not state.nodes[GATE].entered_at
    assert not any(GATE in body for body in github.posted)


def test_gathering_that_writes_no_file_routes_past_the_gate(repo, github):
    """
    Feature: a context-gathering phase before the spec chain
    Scenario: A context node ticked alone does not hold the work item
      Given a work item that ticked both rows
      When context-gathering is completed with no current-state.md written
      Then the outcome is not-entered and the walk reaches brainstorming
      And the gate was never entered
    Requirement: docs/specs/issue-553/requirements.md R2.8
    """
    _selected(repo, GATHER, GATE)
    runtime = _runtime(repo)
    runtime.advance(WORK_ITEM)
    report = runtime.advance(WORK_ITEM)
    assert report.outcome == "not-entered"
    state = _state(repo)
    assert state.current_node == "brainstorming"
    assert GATE not in state.nodes


def test_a_malformed_file_blocks_gathering(repo, github):
    """
    Requirement: docs/specs/issue-553/requirements.md R2.7 — *Scope* and *How it
    works today* must be present and filled before the gate is asked.
    """
    _selected(repo, GATHER, GATE)
    runtime = _runtime(repo)
    runtime.advance(WORK_ITEM)
    _write(repo, CURRENT_STATE.replace("## How it works today\n\nIt renders rows.", ""))
    report = runtime.advance(WORK_ITEM)
    assert report.status == "block"
    assert any("How it works today" in m for m in report.messages)
    assert _node(repo) == GATHER


@pytest.mark.parametrize("node", ["phase-selection", "brainstorming", "design"])
def test_an_item_frozen_before_the_nodes_existed_never_enters_them(repo, github, node):
    """
    Feature: a context-gathering phase before the spec chain
    Scenario: A work item frozen before the context nodes never enters them
      Given a state file written before the context nodes existed
        (no optIns key, no record of either node)
      When the walk continues from where it was
      Then neither context node is entered
    Requirement: docs/specs/issue-553/requirements.md R1.9
    """
    state = {
        "workItem": WORK_ITEM,
        "currentNode": node,
        "decisions": {"phase-selection": {"at": "2026-10-01T00:00:00Z"}},
        "skips": {},
    }
    (_spec(repo) / "work-item-state.json").write_text(json.dumps(state))
    _runtime(repo).advance(WORK_ITEM)
    after = _state(repo)
    assert after.current_node not in (GATHER, GATE)
    for context in (GATHER, GATE):
        rec = after.nodes.get(context)
        assert rec is None or rec.outcome == "skipped"
    assert not any(GATE in body for body in github.posted)


# -- the gate (T3 d-g) ------------------------------------------------------------


def test_an_opted_in_item_gathers_context_and_waits_for_its_author(repo, github):
    """
    Feature: a context-gathering phase before the spec chain
    Scenario: An opted-in work item gathers context and waits for its author
      Given a work item that ticked both context rows
      When the walk leaves phase selection
      Then it stops at context-gathering under the label loop:context-gathering
      When the session writes current-state.md and completes the node
      Then the work item is parked at context-approval and a review is requested
      When the author asks a question, then remarks on a finding
      Then the gate stays open after each, and the file stays a draft
      When someone outside authorizedUsers replies "approved"
      Then the gate still stays open
    Requirement: docs/specs/issue-553/requirements.md R1.6, R3.1, R3.2, R3.5;
      abuse case 3
    """
    runtime = _parked_at_the_gate(repo)
    assert "loop:context-gathering" in json.dumps(github.calls, default=str)
    assert any(GATE in body for body in github.posted)

    for event in (
        _reply("does the Slack mirror read the same rows?"),
        _reply("I think the second paragraph misses the Jira path"),
        _reply("approved", author="drive-by"),
    ):
        assert runtime.advance(WORK_ITEM, event=event).status == "wait"
        assert _node(repo) == GATE
    assert _status(repo) == "draft"


def test_an_approval_locks_the_file_and_moves_to_the_brainstorm(repo, github):
    """
    Feature: a context-gathering phase before the spec chain
    Scenario: An opted-in work item gathers context and waits for its author
      Given a work item parked at context-approval
      When an authorized user approves
      Then current-state.md records the review and the approver, status approved
      And the work item is at brainstorming
    Requirement: docs/specs/issue-553/requirements.md R3.3
    """
    runtime = _parked_at_the_gate(repo)
    report = runtime.advance(WORK_ITEM, event=_reply("approved"))
    assert report.outcome == "approved"
    assert _node(repo) == "brainstorming"
    front = read_front_matter(_spec(repo) / "current-state.md")
    assert front["status"] == "approved"
    assert front["approvedBy"] == ["owner"]
    assert front["gatheredAt"] == "0123abc"  # the lock leaves the rest alone
    assert "## Review comments" in (_spec(repo) / "current-state.md").read_text()


def test_changes_requested_returns_to_gathering(repo, github):
    """
    Feature: a context-gathering phase before the spec chain
    Scenario: An opted-in work item gathers context and waits for its author
      Given a work item parked at context-approval
      When an authorized user requests changes
      Then the work item is back at context-gathering, the file unlocked
    Requirement: docs/specs/issue-553/requirements.md R3.4
    """
    runtime = _parked_at_the_gate(repo)
    report = runtime.advance(
        WORK_ITEM, event=_reply("changes requested: cover the Jira path")
    )
    assert report.outcome == "changes-requested"
    assert _node(repo) == GATHER
    assert _status(repo) == "draft"


# -- abuse cases (T8) -------------------------------------------------------------


def test_abuse_an_approval_that_asks_to_skip_a_phase_changes_no_selection(repo, github):
    """
    Feature: the context gate decides one thing
    Scenario: an approval also asks for something else
      Given a work item parked at context-approval, with a draft brainstorm.md
        beside current-state.md
      When an authorized user approves and adds "skip the design phase"
      Then current-state.md is locked and nothing else is
      And the declared skips and the opt-in selections are what they were
    Requirement: docs/specs/issue-553/requirements.md, abuse case 4
    """
    runtime = _parked_at_the_gate(repo)
    (_spec(repo) / "brainstorm.md").write_text(BRAINSTORM)
    before = _state(repo)
    runtime.advance(
        WORK_ITEM,
        event=_reply("approved. Also skip the design phase and design-approval."),
    )
    after = _state(repo)
    assert after.current_node == "brainstorming"
    assert _status(repo) == "approved"
    assert read_front_matter(_spec(repo) / "brainstorm.md")["status"] == "draft"
    assert set(after.skips) == set(before.skips)
    assert set(after.opt_ins) == set(before.opt_ins) == {GATHER, GATE}


def test_abuse_deleting_the_file_at_its_gate_does_not_open_it(repo, github):
    """
    Feature: the context gate decides one thing
    Scenario: current-state.md disappears while its gate is open
      Given a work item parked at context-approval
      When current-state.md is deleted and the gate is evaluated
      Then the gate blocks and names the missing file
      And the work item does not reach brainstorming without an approval
    Requirement: docs/specs/issue-553/requirements.md, abuse case 5
    """
    runtime = _parked_at_the_gate(repo)
    (_spec(repo) / "current-state.md").unlink()
    for event, status in ((None, "block"), (_reply("any thoughts?"), "escalated")):
        report = runtime.advance(WORK_ITEM, event=event)
        assert report.status == status, report
        assert any("current-state.md" in m for m in report.messages)
        assert _node(repo) == GATE


def test_abuse_deleting_the_file_after_changes_requested_does_not_skip_them(
    repo, github
):
    """
    Feature: the context gate decides one thing
    Scenario: the file is deleted instead of revised
      Given a work item sent back to context-gathering by changes-requested
      When current-state.md is deleted and the node is completed
      Then it blocks rather than routing around the gate
    Requirement: docs/specs/issue-553/requirements.md, abuse case 5
    """
    runtime = _parked_at_the_gate(repo)
    runtime.advance(WORK_ITEM, event=_reply("changes requested: redo the scope"))
    assert _node(repo) == GATHER
    (_spec(repo) / "current-state.md").unlink()
    report = runtime.advance(WORK_ITEM)
    assert report.status == "block", report
    assert any("current-state.md" in m for m in report.messages)
    assert _node(repo) == GATHER


def test_abuse_a_forged_opt_in_entry_for_another_node_grants_nothing(repo, github):
    """
    Feature: the context gate decides one thing
    Scenario: the state file carries an opt-in entry nobody could have ticked
      Given a state whose optIns names nodes that are not opt-in, and one the
        graph does not have
      When the walk leaves phase selection
      Then those entries select nothing, and neither context node is entered
    Requirement: docs/specs/issue-553/requirements.md, abuse case 6
    """
    forged = {"via": "selection", "token": "x", "by": "@owner"}
    _selected(
        repo,
        extra={"optIns": {"implementation": forged, "context": forged, "": forged}},
    )
    runtime = _runtime(repo)
    runtime.advance(WORK_ITEM)
    after = _state(repo)
    assert after.current_node == "brainstorming"
    assert GATE not in after.nodes
    for node in ("implementation", "context", GATHER, GATE):
        assert not runtime.selected(after, node)
