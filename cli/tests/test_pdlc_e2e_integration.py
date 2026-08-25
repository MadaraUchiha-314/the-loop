"""End-to-end PDLC scenario tests (issue-217, T1/T2/T8).

Feature: PDLC process conformance, end to end

One work item per scenario is driven ticket → complete through the REAL
runtime — the shipped ``pdlc-work-item-loop``, the shipped hooks, real artifact
gates in a throwaway checkout — against a scripted agent that plays back
fixtures. Every external system is faked at the seams the existing integration
tests already fake. The fixture-set format and the step vocabulary live in
``test_pdlc_e2e/README.md``; the runner in ``test_pdlc_e2e/runner.py``.

The scenario directories under ``test_pdlc_e2e/scenarios/`` are the suite: a
consistency test asserts every directory has exactly one named test here (and
vice versa), so adding a scenario is a fixture set plus a one-line test naming
it (R2.1) — and a dropped-in set without its test fails loudly (R2.2).
"""

from pathlib import Path
from typing import Callable, Dict

import pytest

from test_pdlc_e2e.runner import (
    FakeIntegration,
    Scenario,
    ScenarioFormatError,
    ScenarioRun,
    match_subsequence,
    scenario_dirs,
)

SCENARIOS = Path(__file__).parent / "test_pdlc_e2e" / "scenarios"

#: scenario-directory name → the named test that runs it (kept in lockstep by
#: test_every_scenario_directory_has_a_named_test).
_COVERED: Dict[str, str] = {}


def covers(name: str):
    def deco(fn):
        _COVERED[name] = fn.__name__
        return fn

    return deco


@pytest.fixture
def run_scenario(tmp_path, monkeypatch) -> Callable[[str], ScenarioRun]:
    def _run(name: str) -> ScenarioRun:
        scenario = Scenario.load(SCENARIOS / name)
        return ScenarioRun(scenario, tmp_path, monkeypatch).execute()

    return _run


# -- the scenarios (T1) ---------------------------------------------------------


@covers("happy-path")
def test_a_tier_3_work_item_walks_the_full_outer_loop(run_scenario):
    """
    Requirement: docs/specs/issue-217/requirements.md#R1, #R2.3
        and docs/specs/issue-281/bugfix.md#AC-1.5
    Scenario: a tier-3 work item flows ticket → complete with no interventions
        Given a work item whose authorized author selects the full process
        And a scripted agent that emits DRAFT spec-chain fixtures phase by phase
        And one inner PR loop simulated at its graph-state file seam
        When each phase is completed and each human gate is approved exactly once
        Then the phases are entered in the configured order with no gate skipped
        And the loop:<phase> label advances at every transition, never regressing
        And the gated artifacts are locked BY the approval gates (issue-281) so
            requirements, design and testing plan say approved before implementation
        And the expected events land in the event log in order
        And the inner loop parks implementation until it completes
    """
    run_scenario("happy-path")


@covers("trivial-tier")
def test_a_trivial_tier_item_short_circuits_with_declared_skips(run_scenario):
    """
    Requirement: docs/specs/issue-217/requirements.md#R2.3
    Scenario: a trivial-tier item completes with declared skips recorded as skips
        Given an authorized selection reply that unticks the spec chain and review chain
        When the item walks implementation, verification and the approval gate only
        Then every removed phase is recorded as skipped with provenance, never as a pass
        And the label trail contains only the walked phases and never regresses
        And verification gates the execution log's Verification results instead of
            passing vacuously with its testing plan declared away
    """
    run_scenario("trivial-tier")


@covers("ask-reply")
def test_an_agent_question_parks_the_run_and_a_reply_resumes_it(run_scenario):
    """
    Requirement: docs/specs/issue-217/requirements.md#R2.3
    Scenario: the agent escalates via the ask seam and the operator's reply resumes it
        Given a work item mid-implementation with a registered session
        When the agent asks a question through the ask seam
        Then session.awaiting_input is recorded with the marked comment posted
        And a reply into a dead pane fails closed without recording a delivery
        And a live reply records session.reply_sent and the run completes
    """
    run_scenario("ask-reply")


@covers("gate-rejection")
def test_a_malformed_artifact_blocks_its_phase_gate(run_scenario):
    """
    Requirement: docs/specs/issue-217/requirements.md#R2.3, issue-281 AC 1.1
    Scenario: a malformed artifact fails the phase gate rather than silently advancing
        Given requirements emitted with the gated Security considerations section missing
        When the agent claims the phase complete
        Then the gate blocks, the pointer and the phase label do not move
        And the repaired artifact advances the run while still a draft — locking
            is the approval gate's act, never the producing node's (issue-281)
    """
    run_scenario("gate-rejection")


@covers("review-rejection")
def test_changes_requested_routes_back_a_phase(run_scenario):
    """
    Requirement: docs/specs/issue-217/requirements.md#R2.3
    Scenario: a changes-requested verdict loops the run back to the design phase
        Given a locked design and testing plan awaiting the design approval gate
        When the authorized reviewer requests changes
        Then the pointer returns to design and the label re-enters loop:design
        And the revised design converges through the same gate on the second pass
    """
    run_scenario("review-rejection")


@covers("gh-unreachable")
def test_a_github_outage_degrades_side_effects_without_changing_verdicts(
    run_scenario,
):
    """
    Requirement: docs/specs/issue-217/requirements.md#R3.3
    Scenario: gh unreachable — events still emitted, side effects reported degraded
        Given the faked GitHub layer failing set-labels and add-comment
        When a human gate approves and the run enters the design phase
        Then the transition happens and its events are recorded
        And the failed label is reported as graph.hook_degraded, not as a block
        And the label trail resumes cleanly after GitHub recovers
    """
    run_scenario("gh-unreachable")


@covers("loop-prevention")
def test_self_authored_and_unauthorized_comments_never_release_a_gate(run_scenario):
    """
    Requirement: docs/specs/issue-217/requirements.md#R2.3, security consideration 2
    Scenario: marked and unauthorized comments are never classified as human input
        Given a work item parked at a human approval gate
        When a comment carrying the self-authorship marker arrives from the owner
        And an approval arrives from an unauthorized author
        Then the gate stays parked through both
        And an unmarked authorized approval then releases it
    """
    run_scenario("loop-prevention")


# -- the harness itself (T2, T8) --------------------------------------------------


def test_every_scenario_directory_has_a_named_test():
    """
    Requirement: docs/specs/issue-217/requirements.md#R2.1, #R2.2
    Scenario: scenario directories and named tests stay in lockstep
        Given the committed scenario directories and the covers registry above
        When the two sets are compared
        Then a fixture set dropped in without its one-line test fails loudly
    """
    assert {d.name for d in scenario_dirs()} == set(_COVERED)


def test_every_committed_scenario_manifest_parses():
    """
    Requirement: docs/specs/issue-217/requirements.md#R2.2
    Scenario: every committed fixture set is well-formed
        Given the scenario directories in the suite
        When each manifest is loaded
        Then each parses and validates without a format error
    """
    for directory in scenario_dirs():
        Scenario.load(directory)  # raises ScenarioFormatError on a bad set


def test_a_scenario_without_a_manifest_is_refused_naming_the_directory(tmp_path):
    """
    Requirement: docs/specs/issue-217/requirements.md#R2.2
    Scenario: a scenario directory without scenario.yaml is refused, not skipped
        Given a scenario directory holding no manifest
        When it is loaded
        Then the refusal names the directory
    """
    with pytest.raises(ScenarioFormatError, match="no scenario.yaml"):
        Scenario.load(tmp_path)


def test_an_unknown_step_kind_is_refused_naming_the_file_and_field(tmp_path):
    """
    Requirement: docs/specs/issue-217/requirements.md#R2.2, security consideration 1
    Scenario: an unknown step kind fails the scenario naming file and field
        Given a manifest whose step vocabulary is outside the closed enum
        When it is loaded
        Then the refusal names the manifest, the step index and the bad kind
    """
    (tmp_path / "scenario.yaml").write_text(
        "name: bad\nworkItem: issue-1\nsteps:\n  - run-shell: {cmd: rm}\n",
        encoding="utf-8",
    )
    with pytest.raises(ScenarioFormatError, match="step 1.*run-shell"):
        Scenario.load(tmp_path)


def test_a_step_naming_a_missing_fixture_is_refused(tmp_path):
    """
    Requirement: docs/specs/issue-217/requirements.md#R2.2
    Scenario: a step naming an absent fixture file is refused at load time
        Given an emit step whose fixture does not exist
        When the manifest is loaded
        Then the refusal names the fixture and where it was looked for
    """
    (tmp_path / "scenario.yaml").write_text(
        "name: bad\nworkItem: issue-1\nsteps:\n"
        "  - emit: {artifact: design.md, fixture: nope.md}\n",
        encoding="utf-8",
    )
    with pytest.raises(ScenarioFormatError, match="missing fixture 'nope.md'"):
        Scenario.load(tmp_path)


def test_the_event_matcher_reports_the_first_divergence():
    """
    Requirement: docs/specs/issue-217/requirements.md#R1.3, #R1.4
    Scenario: the ordered-subsequence matcher names the first missing event
        Given an actual event log and an expected trace it does not satisfy
        When the trace is matched
        Then the report names the expected event's position and name
        And an in-order trace with unrelated events in between matches
    """
    actual = [{"event": "a", "x": 1}, {"event": "noise"}, {"event": "b"}]
    assert match_subsequence(actual, [{"event": "a", "x": 1}, {"event": "b"}]) is None
    # out of order → the divergence names the second expectation
    error = match_subsequence(actual, [{"event": "b"}, {"event": "a"}])
    assert error is not None and "#1" in error and "(a " in error
    # a field mismatch is not a match
    error = match_subsequence(actual, [{"event": "a", "x": 2}])
    assert error is not None and "#0" in error


def test_a_process_regression_fails_the_trace_assertions(tmp_path, monkeypatch):
    """
    Requirement: docs/specs/issue-217/requirements.md#R1.3, #R1.4
    Scenario: a walk that diverges from the expected trace fails, naming the divergence
        Given a world whose observed events describe a walk that skipped a phase
        When the node-trace and label-trail expectations are asserted
        Then each raises naming the index, the expectation and what stood in its place
    """
    from test_pdlc_e2e.runner import ScenarioAssertionError

    scenario = Scenario.load(SCENARIOS / "gate-rejection")
    run = ScenarioRun(scenario, tmp_path, monkeypatch)
    # A forged log: the walk "jumped" phase-selection → design (a phase-skip
    # regression a per-seam test would never see).
    run.events_path.write_text(
        '{"event": "graph.started", "node": "phase-selection"}\n'
        '{"event": "graph.advanced", "node": "phase-selection", "to": "design"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ScenarioAssertionError, match="index 1"):
        run.assert_expect({"nodes": ["phase-selection", "requirements-definition"]})
    run.integration.labels = ["loop:phase-selection", "loop:design"]
    with pytest.raises(ScenarioAssertionError, match="label trail diverges"):
        run.assert_expect(
            {"labels": ["loop:phase-selection", "loop:requirements-definition"]}
        )


def test_the_fake_transport_refuses_operations_outside_its_table():
    """
    Requirement: docs/specs/issue-217/requirements.md#R3.1, security consideration 3
    Scenario: the hermeticity tripwire — an unmodelled operation raises
        Given the fake integration every scenario routes GitHub calls through
        When a hook asks for an operation outside the modelled set
        Then the call raises instead of silently pretending the world answered
    """
    fake = FakeIntegration()
    with pytest.raises(AssertionError, match="unexpected integration operation"):
        fake.call("delete-repository", ref="github:e2e/e2e#1")
