---
type: tasks
phase: tasks-breakdown
workItem: issue-217
status: draft
approvedBy: []
overrides: {}
---

# Tasks: end-to-end PDLC scenario tests

> Derived from [`design.md`](design.md) and [`testing-plan.md`](testing-plan.md).
> Ticket: [#217](https://github.com/MadaraUchiha-314/the-loop/issues/217).

## Task list

- [x] 1. Runner core (`cli/tests/test_pdlc_e2e/runner.py`)
  - `Scenario.load` (manifest parse + validation with file/field-naming
    refusals), `ScenarioRun` (tmp checkout, harness config, FakeIntegration at
    `integrations.resolve`, event log to tmp, session registry seed), the step
    interpreter (`comment`, `emit`, `complete`, `advance`, `ask`, `reply`,
    `inner-loop`, `fail-github`, `restore-github`, `expect`), the trace
    collector and `assert_trace` with first-divergence reporting.
  - _Depends on:_ none
  - _Requirements:_ R1.1–R1.4, R2.1–R2.2, R3.1–R3.3
  - _Test:_ T1, T2 (red→green while authoring the happy path)
- [x] 2. Happy-path scenario (fixtures + expected trace)
  - `scenarios/happy-path/` — locked spec-chain fixtures, execution-log
    fixture with the review-chain sections, full expected node/label/event
    trace.
  - _Depends on:_ 1
  - _Requirements:_ R1.3, R2.3 (happy path)
  - _Test:_ T1
- [x] 3. Trivial-tier + ask-reply scenarios
  - Declared-skip checklist reply; skip provenance assertions. Ask/park/reply
    with session-missing fail-closed check mid-run.
  - _Depends on:_ 2
  - _Requirements:_ R2.3
  - _Test:_ T1
- [x] 4. Error + loop-prevention scenarios
  - `gate-rejection`, `review-rejection`, `gh-unreachable`, `loop-prevention`.
  - _Depends on:_ 2
  - _Requirements:_ R2.3, R3.3, Security 2
  - _Test:_ T1, T8
- [x] 5. Test module + meta-tests + README
  - `cli/tests/test_pdlc_e2e_integration.py` (named tests with Gherkin
    docstrings, scenario-dir↔test consistency check, runner meta-tests),
    `README.md` documenting the fixture-set format.
  - _Depends on:_ 1–4
  - _Requirements:_ R2.1, R2.2, R4.1, R4.3
  - _Test:_ T2, T3
- [x] 6. Docs
  - `docs/capabilities/testing-and-contracts.md` (current behaviour + history
    row); execution-log Documentation/Capability docs sections.
  - _Depends on:_ 1–5
  - _Requirements:_ R4.2
  - _Test:_ T12, T14
- [x] 7. Verification
  - Execute the plan, tick activities with evidence under `evidence/`.
  - _Depends on:_ 1–6
  - _Requirements:_ all
  - _Test:_ the plan itself
