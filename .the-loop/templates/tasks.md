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

Each task is a checkbox, references the requirement(s) it satisfies, and declares its
dependencies so the-loop can build the execution DAG. Keep tasks small and verifiable.

- [ ] 1. <task summary>
  - Details / sub-steps
  - _Depends on:_ none
  - _Requirements:_ R1, R2
- [ ] 2. <task summary>
  - Details / sub-steps
  - _Depends on:_ 1
  - _Requirements:_ R1
- [ ] 3. <task summary>
  - _Depends on:_ 1, 2
  - _Requirements:_ R3

## Dependency graph (DAG)
A quick textual view of the order, e.g. `1 → 2 → 3` (or a mermaid graph).

## Checkpoints
At which task boundaries the-loop runs tests/validations and updates the execution log.
