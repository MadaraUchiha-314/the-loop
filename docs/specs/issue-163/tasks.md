---
type: tasks
phase: tasks-breakdown
workItem: issue-163
status: approved
approvedBy: []
overrides: {}
---

# Tasks: test and verification as nodes in the PDLC

> The last spec artifact. Derived from the locked [`design.md`](design.md) and
> [`testing-plan.md`](testing-plan.md); each `_Test:_` names a matrix row of the plan.

## Task list

- [x] 1. Bundle the `testing-plan.md` template
  - New `skills/the-loop/templates/testing-plan.md` with the four gated sections
    (Test matrix, Verification environment, Evidence plan, Verification results), the
    type catalogue, the activities checklist, and the two security rules
    (credentials by reference; redact evidence).
  - _Depends on:_ none
  - _Requirements:_ R1.4, R2.1, R2.2, R4.2, R5.1
  - _Test:_ T1 — `pytest cli/tests/test_graph_parity.py -k p3` (red→green: P3 fails while
    the template is absent or short a section)
- [x] 2. Add the two nodes to the shipped graph
  - `test-planning` (produces `testing-plan.md`, locked + four sections) between
    `design-approval` and `tasks-breakdown`; `verification` (re-produces
    `testing-plan.md`, `checkmarks: complete` + results section) between
    `implementation` and `self-review`; edges rerouted.
  - _Depends on:_ 1
  - _Requirements:_ R1.1, R1.2, R3.1, R3.2
  - _Test:_ T1 — `pytest cli/tests/test_graph_model.py` (red→green)
- [x] 3. Track the new artifacts in the manifest
  - `docs/specs/<id>/testing-plan.md` @ `test-planning`; `docs/specs/<id>/evidence/`
    as an optional directory.
  - _Depends on:_ 2
  - _Requirements:_ R4.2, R6.2
  - _Test:_ T1 — `pytest cli/tests/test_graph_parity.py -k "p1 or p2"` (red→green: P2
    fails while the graph gates an untracked name)
- [x] 4. Declare the phases in the schema and both configs
  - `workflow.phases` enum + default; this repo's `.the-loop/harness-config.yaml` and
    the bundled `templates/harness-config.yaml`; `tokenEconomy` stage defaults for
    `test-planning` and `verification` in schema and both configs.
  - _Depends on:_ 2
  - _Requirements:_ R6.1, R6.4
  - _Test:_ T1 — `pytest cli/tests/test_graph_parity.py -k p4` (red→green)
- [x] 5. Unit-cover the two nodes, including the not-a-skip regression
  - `cli/tests/test_graph_model.py`: both nodes present with phases and stages, edges
    rerouted, and `verification` declares `produces` so its gate cannot silently skip.
  - _Depends on:_ 2
  - _Requirements:_ R3.1, R3.2
  - _Test:_ T1 — `pytest cli/tests/test_graph_model.py`
- [x] 6. Integration-cover the verification gate end to end
  - New `cli/tests/test_graph_verification_integration.py` driving the real hook chain
    over a temporary spec folder: unticked activity blocks, empty results blocks,
    complete plan passes. Gherkin docstrings, `Requirement:` links.
  - _Depends on:_ 2, 1
  - _Requirements:_ R3.2, R3.3
  - _Test:_ T2 — `pytest cli/tests/test_graph_verification_integration.py` (red→green)
- [x] 7. Render the new sequence in the skill and references
  - `SKILL.md` (artifact chain, phase sequence, principles, command list),
    `reference/workflow.md` (phases, the two nodes, evidence), `reference/testing.md`
    (the plan, the catalogue, evidence and redaction, the facilitate-don't-own rule),
    `reference/context.md` phase list.
  - _Depends on:_ 2
  - _Requirements:_ R6.3, R4.3, R5.2, R5.3
  - _Test:_ T3 — `make lint` (markdownlint) + review
- [x] 8. Wire the commands
  - New `commands/create-testing-plan.md` and `commands/verify-work.md`; chain them from
    `create-design.md`, `create-tasks-plan.md`, `execute-tasks.md` and `work-on.md`;
    `init.md` creates the two new labels.
  - _Depends on:_ 2, 7
  - _Requirements:_ R1.1, R3.1, R6.3
  - _Test:_ T3 — `make lint` + review
- [x] 9. Update the templates the loop authors from
  - `design.md` (Testing strategy points at the plan), `tasks.md` (`_Test:_` names a
    matrix row), `execution-log.md` (phase enum, transition rows).
  - _Depends on:_ 2
  - _Requirements:_ R1.3, R6.3
  - _Test:_ T1 — `pytest cli/tests/test_graph_parity.py` (P3 covers the templates)
- [x] 10. Fold in the capability docs and the decision record
  - `docs/capabilities/testing-and-contracts.md` (the plan + verification node),
    `spec-workflow.md`, `process-graph.md`, `capabilities.md` index;
    `docs/reports/labels-and-dashboards.md`; `docs/decisions/decision-060.md` + index;
    guide/README/architecture phase sequences.
  - _Depends on:_ 7
  - _Requirements:_ R6.3
  - _Test:_ T3 — `make lint` + review
- [x] 11. **Added during implementation:** a `skip` must not short-circuit a chain
  - Found while writing T6: `run_chain` stopped at the first non-`pass` result, including
    `skip`, so hooks behind a skipping one never ran and a chain _ending_ in a skip routed
    on the outcome `"skip"` — for which no edge is declared. `implementation` (chain ends
    in a no-op `verify-tests`) therefore parked at `no_edge`, making the
    `implementation → verification` edge unreachable. Fixed in `graph/chain.py`.
  - _Depends on:_ 2
  - _Requirements:_ R3.1
  - _Test:_ T1 — `pytest cli/tests/test_graph_chain.py -k Skip`; T2 —
    `test_implementation_reaches_verification_rather_than_parking` (red→green)
- [x] 12. Dogfood: this work item's own testing plan, executed
  - `docs/specs/issue-163/testing-plan.md` authored at planning and completed at
    verification with results + evidence under `docs/specs/issue-163/evidence/`.
  - _Depends on:_ 1–11
  - _Requirements:_ R4.1, R4.2, R4.5
  - _Test:_ T1, T2, T3 — the full suite, recorded as evidence

## Dependency graph (DAG)

```text
1 → 2 → 3
      → 4
      → 5
      → 6 (also ← 1)
      → 11
      → 7 → 8
      → 9
        7 → 10
1..11 → 12
```

## Checkpoints

After tasks 2–6 (the executable surface) run `make test`; after 7–10 run `make lint`.
Task 12 is the `verification` node itself: the full suite plus lint, recorded in the
plan's **Verification results** with committed evidence, before the review chain runs.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
