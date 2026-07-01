---
type: tasks
phase: tasks-breakdown
workItem: ""
status: draft                # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Tasks: <work item title>

> Phase 3 of 3 (requirements → design → tasks). A DAG of implementation tasks derived
> from the approved design. MUST be reviewed/approved before implementation begins.
> Once approved, the-loop executes these end-to-end with minimal/no intervention.

## Task list

Each task is a checkbox, references the requirement(s) it satisfies, declares its
dependencies so the-loop can build the execution DAG, and names the **test(s) that will
prove it**. Keep tasks small and verifiable. TDD invariant (`tdd.mode`): **no production
code without a failing test that motivates it** — write/adjust the test first, watch it go
red, then make it green.

- [ ] 1. <task summary>
  - Details / sub-steps
  - _Depends on:_ none
  - _Requirements:_ R1, R2
  - _Test:_ <test that proves this task, e.g. `pytest tests/test_x.py::test_y`> (red→green)
- [ ] 2. <task summary>
  - Details / sub-steps
  - _Depends on:_ 1
  - _Requirements:_ R1
  - _Test:_ <test command / case>
- [ ] 3. <task summary>
  - _Depends on:_ 1, 2
  - _Requirements:_ R3
  - _Test:_ <test command / case>

## Dependency graph (DAG)

A quick textual view of the order, e.g. `1 → 2 → 3` (or a mermaid graph).

## Checkpoints

At which task boundaries the-loop runs tests/validations and updates the execution log.
Record each task's test command and its **red→green** transition as evidence (`tdd.mode`).
