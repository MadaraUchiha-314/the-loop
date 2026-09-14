"""End-to-end: the six review-chain nodes gate the record they leave (issue-167).

Feature: the review chain gates the record it is supposed to produce

Driven against the **shipped** `pdlc.yaml`, not a fixture graph, because what is
under test is the node declarations themselves. Before issue-167 every one of
these six nodes declared `sections:` and no artifact, so `validate-artifacts`
resolved nothing, returned *skipped*, and — a skip not being a decision
(decision-060) — the chain passed straight through. `security-review` is
annotated "never skippable, at any risk tier"; it skipped on every run.

The subject was one shared `execution-log.md` until issue-365 retired it. Each
node now gates ONE file of its own under `evidence/`, which is the same gate with
a property the shared log did not have: no node's assertion can be satisfied by
another node's writing, and a declared skip removes exactly one assertion.

`Runtime.evaluate` is pure by contract: no network, no subprocess, no mutation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.model import load_graph
from the_loop.graph.runtime import Runtime

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / "skills" / "the-loop" / "templates" / "evidence"

#: Node → the record it gates and the section(s) it demands of it, as the shipped
#: graph declares it. A node may gate more than one section: `capability-docs`
#: gates both the organized view of specs and the user-facing docs (issue-174,
#: decision-066).
GATED = {
    "self-review": ("evidence/self-review.md", ("Review cycles",)),
    "critic-review": ("evidence/critic-review.md", ("Review cycles",)),
    "security-review": ("evidence/security-review.md", ("Security review (gate)",)),
    "evidence": ("evidence/final-validation.md", ("Final validation evidence",)),
    "capability-docs": (
        "evidence/documentation.md",
        ("Capability docs", "Documentation"),
    ),
    "reviewer-briefing": ("evidence/pull-requests.md", ("Pull requests",)),
}

HEADER = "---\ntype: evidence\nworkItem: issue-1\n---\n\n# Record\n\n"


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / "issue-1" / "evidence").mkdir(parents=True)
    return tmp_path


def _record(repo, name: str, body: str) -> None:
    path = repo / "docs" / "specs" / "issue-1" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER + body, encoding="utf-8")


def _evaluate(repo, node_id: str, skips=None):
    runtime = Runtime(repo, graph=load_graph(), config={})
    return runtime.evaluate(node_id, runtime.work_item("issue-1"), skips=skips or {})


@pytest.mark.parametrize("node_id", sorted(GATED))
def test_a_review_node_blocks_when_its_section_was_never_written(repo, node_id):
    """
    Feature: the review chain gates the record it is supposed to produce
    Scenario: a review node will not pass on a record missing its section
      Given a work item whose record for this node carries something else
      When the node's exit chain is evaluated
      Then it blocks, naming the section it gates and the file it looked in
    Requirement: docs/specs/issue-167/requirements.md#R3.2
    """
    name, sections = GATED[node_id]
    _record(repo, name, "## Something else\n\nnot what this gate reads\n")
    outcome = _evaluate(repo, node_id)
    assert outcome.status == "block", (
        f"{node_id} passed a record with none of its {sections!r} sections — "
        "the gate is reporting success without reading anything"
    )
    rendered = " | ".join(m.render() for m in outcome.messages)
    for section in sections:
        assert section in rendered
    assert name in rendered


@pytest.mark.parametrize("node_id", sorted(GATED))
def test_a_review_node_passes_once_its_section_carries_a_record(repo, node_id):
    """
    Feature: the review chain gates the record it is supposed to produce
    Scenario: a review node passes on a record whose section was written
      Given the record this node gates, carrying its section with content
      When the node's exit chain is evaluated
      Then it passes
    Requirement: docs/specs/issue-167/requirements.md#R3.1
    """
    name, sections = GATED[node_id]
    _record(
        repo,
        name,
        "".join(
            f"## {section}\n\na real record of what happened\n\n"
            for section in sections
        ),
    )
    assert _evaluate(repo, node_id).status == "pass"


def test_capability_docs_blocks_when_only_one_of_its_two_sections_is_written(repo):
    """
    Feature: the review chain gates the record it is supposed to produce
    Scenario: a node gating two sections is not satisfied by one of them
      Given a record naming the capability docs but not the user-facing docs
      When the capability-docs node's exit chain is evaluated
      Then it blocks, naming the section that is missing and not the one present
    Requirement: docs/specs/issue-174/requirements.md#R4.2

    The point of issue-174: a work item that folded in its capability docs and left
    the README describing the previous process must not reach `complete`. Asserted in
    both directions so neither section can quietly stand in for the other.
    """
    name, _ = GATED["capability-docs"]
    for present, missing in (
        ("Capability docs", "Documentation"),
        ("Documentation", "Capability docs"),
    ):
        _record(repo, name, f"## {present}\n\na real record of what happened\n")
        outcome = _evaluate(repo, "capability-docs")
        assert outcome.status == "block", (
            f"capability-docs passed on a record carrying only {present!r} — "
            f"{missing!r} is gated too"
        )
        rendered = " | ".join(m.render() for m in outcome.messages)
        assert missing in rendered


@pytest.mark.parametrize("node_id", sorted(GATED))
def test_a_review_node_blocks_when_the_record_is_absent_entirely(repo, node_id):
    """
    Feature: the review chain gates the record it is supposed to produce
    Scenario: a validated artifact that does not exist blocks rather than skipping
      Given a work item whose spec folder carries no record for this node
      When the node's exit chain is evaluated
      Then it blocks, naming the missing file
    Requirement: docs/specs/issue-167/requirements.md#R1.2
    """
    name, _ = GATED[node_id]
    outcome = _evaluate(repo, node_id)
    assert outcome.status == "block"
    assert any(name in m.render() for m in outcome.messages)


def test_one_nodes_record_never_satisfies_another_nodes_gate(repo):
    """
    Feature: the review chain gates the record it is supposed to produce
    Scenario: the self-review's rounds do not clear the critic's gate
      Given a work item whose self-review record is written and nothing else
      When the critic-review node's exit chain is evaluated
      Then it blocks on its own missing record
    Requirement: docs/specs/issue-365/requirements.md#R2.1

    The property one file per node buys (issue-365, decision-126). `self-review`
    and `critic-review` both gate a `Review cycles` section, and on the shared
    execution log the first to write one satisfied both.
    """
    _record(repo, "evidence/self-review.md", "## Review cycles\n\none round\n")
    assert _evaluate(repo, "self-review").status == "pass"
    outcome = _evaluate(repo, "critic-review")
    assert outcome.status == "block"
    assert any("evidence/critic-review.md" in m.render() for m in outcome.messages)


def test_a_declared_skip_relaxes_only_its_own_nodes_gate(repo):
    """
    Feature: the review chain gates the record it is supposed to produce
    Scenario: declaring the self-review away leaves the critic's gate standing
      Given a work item that declared `self-review` away at phase-selection
      When the critic-review node's exit chain is evaluated with nothing written
      Then it still blocks
    Requirement: docs/specs/issue-365/requirements.md#R2.3

    A skipped node is routed past and its own chain never runs, so the only way a
    skip could reach a *walked* node's gate is a shared subject. There is none.
    """
    skips = {"self-review": {"via": "selection", "token": "self-review"}}
    assert _evaluate(repo, "critic-review", skips=skips).status == "block"


def test_a_legacy_execution_log_changes_nothing(repo):
    """
    Feature: the review chain gates the record it is supposed to produce
    Scenario: a work item carrying the retired execution log is gated as any other
      Given a spec folder holding an execution-log.md with every old section
      When each review node's exit chain is evaluated
      Then every one of them still blocks on its own record
    Requirement: docs/specs/issue-365/requirements.md#R5.3

    Existing logs are the operator's data and stay where they are; nothing in
    the-loop reads them, so one on disk neither satisfies a gate nor breaks one.
    """
    legacy = "\n".join(
        f"## {section}\n\nwritten under the old shape\n"
        for _, sections in GATED.values()
        for section in sections
    )
    _record(repo, "execution-log.md", legacy)
    for node_id, (name, _) in GATED.items():
        outcome = _evaluate(repo, node_id)
        assert outcome.status == "block", f"{node_id} read the retired log"
        assert any(name in m.render() for m in outcome.messages)


@pytest.mark.skipif(not TEMPLATES.is_dir(), reason="plugin tree not present")
@pytest.mark.parametrize("node_id", sorted(GATED))
def test_the_bundled_template_can_clear_every_gate_in_the_chain(repo, node_id):
    """
    Feature: the review chain gates the record it is supposed to produce
    Scenario: the template an agent authors from passes the gate it is authored for
      Given the bundled evidence template for this node, unedited
      When the node's exit chain is evaluated
      Then it passes
    Requirement: docs/specs/issue-167/requirements.md#R3.3

    The latent half of issue-167: `capability-docs` gated a section the template
    did not offer, so the day the node stopped skipping, every work item would
    have blocked there.
    """
    name, _ = GATED[node_id]
    template = TEMPLATES / Path(name).name
    _record(repo, name, template.read_text(encoding="utf-8").split("---\n", 2)[-1])
    assert _evaluate(repo, node_id).status == "pass"
