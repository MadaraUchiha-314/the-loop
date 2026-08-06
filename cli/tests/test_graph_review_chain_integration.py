"""End-to-end: the six review-chain nodes gate the shared execution log (issue-167).

Feature: the review chain gates the record it is supposed to produce

Driven against the **shipped** `pdlc.yaml`, not a fixture graph, because what is
under test is the node declarations themselves. Before this work item every one
of these six nodes declared `sections:` and no artifact, so `validate-artifacts`
resolved nothing, returned *skipped*, and — a skip not being a decision
(decision-060) — the chain passed straight through. `security-review` is
`required: true` and annotated "never skippable, at any risk tier"; it skipped on
every run.

`Runtime.evaluate` is pure by contract: no network, no subprocess, no mutation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.model import load_graph
from the_loop.graph.runtime import Runtime

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "skills" / "the-loop" / "templates" / "execution-log.md"

#: Node → the execution-log section it gates, as the shipped graph declares it.
GATED = {
    "self-review": "Review cycles",
    "critic-review": "Review cycles",
    "security-review": "Security review (gate)",
    "evidence": "Final validation evidence",
    "capability-docs": "Capability docs",
    "reviewer-briefing": "Pull requests",
}

HEADER = "---\ntype: execution-log\nworkItem: issue-1\nphase: needs-review\nstatus: in-progress\n---\n\n# Execution Log\n\n"


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / "issue-1").mkdir(parents=True)
    return tmp_path


def _log(repo, body: str) -> None:
    (repo / "docs" / "specs" / "issue-1" / "execution-log.md").write_text(
        HEADER + body, encoding="utf-8"
    )


def _evaluate(repo, node_id: str):
    runtime = Runtime(repo, graph=load_graph(), config={})
    return runtime.evaluate(node_id, runtime.work_item("issue-1"))


@pytest.mark.parametrize("node_id", sorted(GATED))
def test_a_review_node_blocks_when_its_section_was_never_written(repo, node_id):
    """
    Feature: the review chain gates the record it is supposed to produce
    Scenario: a review node will not pass on an execution log missing its section
      Given a work item whose execution log carries only progress entries
      When the node's exit chain is evaluated
      Then it blocks, naming the section it gates and the log it looked in
    Requirement: docs/specs/issue-167/requirements.md#R3.2
    """
    _log(repo, "## Progress entries\n\n### t — did a thing\n")
    outcome = _evaluate(repo, node_id)
    assert outcome.status == "block", (
        f"{node_id} passed an execution log with no {GATED[node_id]!r} section — "
        "the gate is reporting success without reading anything"
    )
    rendered = " | ".join(m.render() for m in outcome.messages)
    assert GATED[node_id] in rendered
    assert "execution-log.md" in rendered


@pytest.mark.parametrize("node_id", sorted(GATED))
def test_a_review_node_passes_once_its_section_carries_a_record(repo, node_id):
    """
    Feature: the review chain gates the record it is supposed to produce
    Scenario: a review node passes on a log whose section was written
      Given an execution log carrying the section the node gates, with content
      When the node's exit chain is evaluated
      Then it passes
    Requirement: docs/specs/issue-167/requirements.md#R3.1
    """
    _log(repo, f"## {GATED[node_id]}\n\na real record of what happened\n")
    assert _evaluate(repo, node_id).status == "pass"


@pytest.mark.parametrize("node_id", sorted(GATED))
def test_a_review_node_blocks_when_the_log_is_absent_entirely(repo, node_id):
    """
    Feature: the review chain gates the record it is supposed to produce
    Scenario: a validated artifact that does not exist blocks rather than skipping
      Given a work item whose spec folder has no execution log at all
      When the node's exit chain is evaluated
      Then it blocks, naming the missing file
    Requirement: docs/specs/issue-167/requirements.md#R1.2
    """
    outcome = _evaluate(repo, node_id)
    assert outcome.status == "block"
    assert any("execution-log.md" in m.render() for m in outcome.messages)


@pytest.mark.skipif(not TEMPLATE.is_file(), reason="plugin tree not present")
@pytest.mark.parametrize("node_id", sorted(GATED))
def test_the_bundled_template_can_clear_every_gate_in_the_chain(repo, node_id):
    """
    Feature: the review chain gates the record it is supposed to produce
    Scenario: the template an agent authors from can pass all six gates
      Given the bundled execution-log template, unedited
      When each review node's exit chain is evaluated
      Then every one of them passes
    Requirement: docs/specs/issue-167/requirements.md#R3.3

    The latent half of issue-167: `capability-docs` gated a section the template
    did not offer, so the day the node stopped skipping, every work item would
    have blocked there.
    """
    _log(repo, TEMPLATE.read_text(encoding="utf-8").split("---\n", 2)[-1])
    assert _evaluate(repo, node_id).status == "pass"
