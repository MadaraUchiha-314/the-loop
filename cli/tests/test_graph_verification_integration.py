"""End-to-end: the `test-planning` and `verification` gates of the shipped graph.

Feature: testing is planned and verified as nodes of the PDLC

Driven against the **shipped** `pdlc.yaml` rather than a fixture graph, because
what is under test is the node declarations themselves — that they gate on the
sections the bundled template offers, and that `verification` re-declares
`testing-plan.md` so its gate actually runs instead of skipping (issue-163).

`Runtime.evaluate` is pure by contract: no network, no subprocess, no mutation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.model import load_graph
from the_loop.graph.runtime import Runtime

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "skills" / "the-loop" / "templates" / "testing-plan.md"

PLANNED = """---
type: testing-plan
phase: test-planning
workItem: issue-1
status: approved
---

# Testing plan: a work item

## Test matrix

| # | Type | Applies? | Scope | Where |
|---|------|----------|-------|-------|
| T1 | Unit | yes | the parser | `pytest` |
| T7 | Performance | n/a — no hot path is touched | | |

## Verification environment

This repository only. Credentials: `THE_LOOP_TOKEN` (by reference).

## Evidence plan

T1 → `evidence/unit.txt`.

## Verification activities

- [ ] T1 — `pytest`

## Verification results

_Not yet executed._
"""

EXECUTED = PLANNED.replace("- [ ] T1", "- [x] T1").replace(
    "_Not yet executed._",
    "| T1 | `pytest` | 12 passed | [unit.txt](evidence/unit.txt) |",
)


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / "issue-1").mkdir(parents=True)
    return tmp_path


def _spec(repo) -> Path:
    return repo / "docs" / "specs" / "issue-1"


def _runtime(repo) -> Runtime:
    return Runtime(repo, graph=load_graph(), config={})


def _evaluate(repo, node_id: str):
    runtime = _runtime(repo)
    return runtime.evaluate(node_id, runtime.work_item("issue-1"))


def test_planning_blocks_until_the_plan_exists(repo):
    """
    Feature: testing is planned and verified as nodes of the PDLC
    Scenario: the test-planning node will not pass without a plan
      Given a work item whose spec folder has no testing plan
      When the test-planning node's exit chain is evaluated
      Then it blocks and names the missing artifact
      When the plan is written, still in draft
      Then it passes — the plan is locked later, at design-approval, by the
        gate that classifies the human's one approval (issue-281)
    Requirement: docs/specs/issue-163/requirements.md#R1,
        docs/specs/issue-281/bugfix.md#AC-1.1
    """
    missing = _evaluate(repo, "test-planning")
    assert missing.status == "block"
    assert any("testing-plan.md" in m.render() for m in missing.messages)

    (_spec(repo) / "testing-plan.md").write_text(
        PLANNED.replace("status: approved", "status: draft"), encoding="utf-8"
    )
    assert _evaluate(repo, "test-planning").status == "pass"


def test_planning_passes_once_the_four_sections_are_authored(repo):
    """
    Feature: testing is planned and verified as nodes of the PDLC
    Scenario: a locked plan carrying the gated sections clears the planning node
      Given a locked testing plan with matrix, environment, evidence and results
      When the test-planning node's exit chain is evaluated
      Then it passes, and the results heading is present but not yet filled
    Requirement: docs/specs/issue-163/requirements.md#R1.2
    """
    (_spec(repo) / "testing-plan.md").write_text(PLANNED, encoding="utf-8")
    assert _evaluate(repo, "test-planning").status == "pass"


def test_an_empty_results_section_blocks_the_planning_gate(repo):
    """
    Feature: testing is planned and verified as nodes of the PDLC
    Scenario: the results heading must be authored holding something
      Given a locked plan whose Verification results heading has no body
      When the test-planning node's exit chain is evaluated
      Then it blocks on the empty section
    Requirement: docs/specs/issue-163/requirements.md#R1.2
    """
    (_spec(repo) / "testing-plan.md").write_text(
        PLANNED.replace("_Not yet executed._", ""), encoding="utf-8"
    )
    outcome = _evaluate(repo, "test-planning")
    assert outcome.status == "block"
    assert any("Verification results" in m.render() for m in outcome.messages)


def test_verification_blocks_while_a_planned_activity_is_unticked(repo):
    """
    Feature: testing is planned and verified as nodes of the PDLC
    Scenario: an activity that was planned but not executed keeps the gate shut
      Given a locked plan whose only activity is still unticked
      When the verification node's exit chain is evaluated
      Then it blocks, counting the outstanding activity
    Requirement: docs/specs/issue-163/requirements.md#R3.3
    """
    (_spec(repo) / "testing-plan.md").write_text(PLANNED, encoding="utf-8")
    outcome = _evaluate(repo, "verification")
    assert outcome.status == "block"
    assert any("still unticked" in m.render() for m in outcome.messages)


def test_verification_passes_once_the_plan_is_executed_and_recorded(repo):
    """
    Feature: testing is planned and verified as nodes of the PDLC
    Scenario: an executed plan with recorded results clears the verification node
      Given a plan whose activities are all ticked
      And whose Verification results record the command, outcome and evidence
      When the verification node's exit chain is evaluated
      Then it passes
    Requirement: docs/specs/issue-163/requirements.md#R3.2
    """
    (_spec(repo) / "testing-plan.md").write_text(EXECUTED, encoding="utf-8")
    assert _evaluate(repo, "verification").status == "pass"


def test_implementation_reaches_verification_rather_than_parking(repo):
    """
    Feature: testing is planned and verified as nodes of the PDLC
    Scenario: the implementation node routes to verification on a pass
      Given a work item whose tasks are all ticked
      When the implementation node's exit chain is evaluated
      Then the chain passes despite ending in a verify-tests hook that skips
      And the declared edge leads to the verification node
    Requirement: docs/specs/issue-163/requirements.md#R3.1
    """
    (_spec(repo) / "tasks.md").write_text(
        "---\nstatus: approved\n---\n\n# Tasks\n\n## Task list\n\n- [x] 1. done\n",
        encoding="utf-8",
    )
    outcome = _evaluate(repo, "implementation")
    assert outcome.status == "pass", (
        "a chain ending in a skipping hook must still pass — otherwise the "
        "outcome is 'skip', no edge is declared for it, and the node escalates"
    )
    assert load_graph().next_node("implementation", outcome.outcome) == "verification"


@pytest.mark.skipif(not TEMPLATE.is_file(), reason="plugin tree not present")
def test_the_bundled_template_clears_the_planning_gate_once_locked(repo):
    """
    Feature: testing is planned and verified as nodes of the PDLC
    Scenario: the template an agent authors from can pass its own gate
      Given the bundled testing-plan template, locked
      When the test-planning node's exit chain is evaluated
      Then it passes
    Requirement: docs/specs/issue-163/requirements.md#R1.4
    """
    text = TEMPLATE.read_text(encoding="utf-8").replace(
        "status: draft", "status: approved", 1
    )
    (_spec(repo) / "testing-plan.md").write_text(text, encoding="utf-8")
    assert _evaluate(repo, "test-planning").status == "pass"


# -- issue-179: the plan is selectable, so the gate must follow the proof -------

SKIPPED_PLAN = {"test-planning": {"via": "selection", "by": "@owner"}}

LOG = """# Execution Log: a work item

## Progress entries

### t — did a thing

## Verification results

{results}

## Review cycles
"""


def _log(repo, results: str) -> None:
    (_spec(repo) / "execution-log.md").write_text(
        LOG.format(results=results), encoding="utf-8"
    )


def _evaluate_skipped(repo, node_id: str):
    runtime = _runtime(repo)
    return runtime.evaluate(node_id, runtime.work_item("issue-1"), skips=SKIPPED_PLAN)


def test_verification_gates_the_log_when_the_plan_was_declared_away(repo):
    """
    Feature: a kept gate keeps a subject (issue-179)
    Scenario: verification is walked by a work item that skipped test-planning
      Given a work item whose test-planning node was declared skipped
      And no testing-plan.md, because the phase that authors it never ran
      When the verification node's exit chain is evaluated
      Then it blocks, naming the execution log rather than passing vacuously
      When the log records what was verified
      Then it passes
    Requirement: docs/specs/issue-179/requirements.md R2.2
    """
    _log(repo, "")
    empty = _evaluate_skipped(repo, "verification")
    assert empty.status == "block", (
        "the plan's absence is planned, so the artifact gate skips — if nothing "
        "else asserts, a mandatory node reports success having run nothing"
    )
    assert any("execution-log.md" in m.render() for m in empty.messages)

    _log(repo, "| markdownlint | `npx markdownlint-cli2` | pass | ci log |")
    assert _evaluate_skipped(repo, "verification").status == "pass"


def test_verification_gates_the_plan_alone_when_one_exists(repo):
    """
    Feature: a kept gate keeps a subject (issue-179)
    Scenario: a declared skip that produced an artifact anyway
      Given test-planning was declared skipped but a testing-plan.md exists
      When the verification node's exit chain is evaluated
      Then the plan is gated exactly as it would be without the declaration
      And the execution log's Verification results are not demanded twice
    Requirement: docs/specs/issue-179/requirements.md R2.3
    """
    _log(repo, "")
    (_spec(repo) / "testing-plan.md").write_text(PLANNED, encoding="utf-8")
    blocked = _evaluate_skipped(repo, "verification")
    assert blocked.status == "block"
    assert any("still unticked" in m.render() for m in blocked.messages)
    assert not any("execution-log.md" in m.render() for m in blocked.messages)

    (_spec(repo) / "testing-plan.md").write_text(EXECUTED, encoding="utf-8")
    assert _evaluate_skipped(repo, "verification").status == "pass"


def test_verification_ignores_the_log_when_the_plan_was_kept(repo):
    """
    Feature: a kept gate keeps a subject (issue-179)
    Scenario: the ordinary path is untouched by the conditional entry
      Given a work item that kept test-planning and executed its plan
      And an execution log whose Verification results section is empty
      When the verification node's exit chain is evaluated
      Then it passes — the fallback applies only to a planned absence
    Requirement: docs/specs/issue-179/requirements.md R2.1
    """
    _log(repo, "")
    (_spec(repo) / "testing-plan.md").write_text(EXECUTED, encoding="utf-8")
    assert _evaluate(repo, "verification").status == "pass"
