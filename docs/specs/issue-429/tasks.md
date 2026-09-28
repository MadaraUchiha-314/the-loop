---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#429"
status: in-review
approvedBy: []
overrides: {}
riskTier: 3
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: the stop gate blocks on a node the work item never entered

> Phase 4 of 4. Each task names the requirement it satisfies and the testing-plan row
> that proves it.

## Task list

- [x] **A0: reproduce.** The bugfix's console session on `main` at `48cb8e6`: `check`
      says `phase-selection`, and the gate exits 2 demanding `design.md`. *Req:* all ·
      *Test:* T8.
- [x] **A1: `pointer` on the report.** `StatusReport.pointer` from
      `state.current_node`, emitted by `as_dict`. *Req:* R3.1, R3.2, R3.4 ·
      *Test:* T3.
- [x] **A2: the gate walks to the pointer.** `blocking_node`: inconclusive without a
      resolvable `currentNode` or `pointer`; the first unsatisfied node at or before
      the pointer, if `block`; `currentNode` as the bound when there is no `pointer`
      key. The `run_check` docstring is restated. *Deps:* A1 · *Req:* R1, R2 ·
      *Test:* T1, T2, T4, T6.
- [x] **A3: the table says both.** `_state_line` names the pointer under `--recompute`
      when it differs. *Deps:* A1 · *Req:* R3.3 · *Test:* T5.
- [x] **A4: tests.** New cases in `test_harness_gate.py`; the new module
      `test_gate_pointer_integration.py`; the key pin in `test_core_graphs.py`.
      *Deps:* A1–A3 · *Test:* T1–T7.
- [x] **B1: interface docs.** `POST /graph/check`'s description (route and OpenAPI
      contract), the `check_work_item` MCP tool. *Deps:* A1 · *Test:* T11.
- [x] **C1: capability and CLI docs.** `docs/capabilities/process-graph.md` gets the
      requirement and a history row; `docs/capabilities/cli.md`,
      `docs/cli/commands/check.md` and `skills/the-loop/reference/automation.md` are
      updated. *Deps:* A2, A3 · *Test:* T10.
- [x] **D1: evidence.** `verification.md`, `self-review.md`, `security-review.md`,
      `documentation.md`, `reviewer-briefing.md`. *Deps:* A0–C1.
