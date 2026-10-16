---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#494"
status: draft                # no approval gate follows this node (issue-281)
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: gate the brainstorm on its author's approval

> Derived from [`bugfix.md`](bugfix.md), [`design.md`](design.md) and
> [`testing-plan.md`](testing-plan.md). All the work is in this repository. Each code task
> is test-first: its named test goes red, then green.

## Task list

- [x] **A1: `absentOutcome` on `validate-artifacts`.** Add the parameter to the
  optional-node branch in `cli/the_loop/graph/hooks/artifacts.py`.
  - _Depends on:_ none
  - _Requirements:_ R2.1, R2.4
  - _Test:_ T2
- [x] **A2: the graph.** Add `brainstorm-approval` to `pdlc-work-item-loop.yaml`, set
  `absentOutcome: not-entered` on `brainstorming`'s exit, re-point the edges per the
  design's table, and add the node to `spec-chain`. Update the pinned tests
  (`test_graph_skips.py`, `test_core_graphs.py`) and the e2e scenario node lists.
  - _Depends on:_ A1
  - _Requirements:_ R1.1, R1.4, R1.5, R2.2, R2.3
  - _Test:_ T1, T5
- [x] **A3: the runtime walk.** Add the T3/T4 integration tests that walk the gate.
  - _Depends on:_ A2
  - _Requirements:_ R1.2, R1.3, R1.4, R1.6, R2.1, R2.2, R2.3
  - _Test:_ T3, T4
- [x] **A4: the checklist fixtures.** Regenerate or edit the Jira checklist fixtures and
  any selection test that pins the row list.
  - _Depends on:_ A2
  - _Requirements:_ R2.3
  - _Test:_ T6
- [x] **A5: the documentation.** Update the files in the design's documentation table,
  including the `brainstorm.md` template, and `docs/capabilities/spec-workflow.md`.
  - _Depends on:_ A2
  - _Requirements:_ R3.1, R3.2
  - _Test:_ T9
- [x] **A6: verify.** Run the testing plan's activities and record the evidence.
  - _Depends on:_ A3, A4, A5
  - _Requirements:_ all
  - _Test:_ T7, T8
