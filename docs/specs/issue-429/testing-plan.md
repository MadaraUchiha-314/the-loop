---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#429"
status: in-review            # draft | in-review | approved — locked with bugfix.md
approvedBy: []
overrides: {}
riskTier: 3
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: the stop gate blocks on a node the work item never entered

> Derived from [`bugfix.md`](bugfix.md) and [`design.md`](design.md). Planned at
> `test-planning`, results recorded at `verification`. See
> [`evidence/verification.md`](evidence/verification.md).

## What "proved" means here

The defect is a wrong *block*, so both directions have to be pinned.

- The gate lets a parked item's turn end.
- It still blocks an item that is at the unmet node, and on a broken node behind a
  moved pointer.

The ticket's reproduction must be run as the harness runs it: the gate script in a
subprocess, invoking the real CLI. It must fail on the unfixed tree (negative control).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (`blocking_node`) | yes | pointer behind the derived position → no block; pointer at it → block; pointer ahead of a broken node → blocks on that node; `wait` before the pointer → no block; empty/`None`/unknown pointer → inconclusive; `currentNode` `""`/`None`/unknown → inconclusive with and without a pointer; issue-238's position-unknown answer → inconclusive (R1, R2) | `tests/test_harness_gate.py` |
| T2 | Unit (old CLI) | yes | a report with no `pointer` key keeps the pre-change behaviour: every existing `blocking_node`/`main` test unchanged and green (R2.3) | `tests/test_harness_gate.py` |
| T3 | Integration (report) | yes | a real checkout: `pointer` in both modes, `""` with no state file, derived `currentNode` unchanged; issue-238's answer keeps six keys; the key pin moves by one (R3.1, R3.2, R3.4) | `tests/test_gate_pointer_integration.py`, `tests/test_core_graphs.py` |
| T4 | Integration (gate on a real report) | yes | the ticket's state on the shipped graph → no block; the same item at `design` → block naming `design.md`; pointer at `implementation` → blocks on `design` (R1) | `tests/test_gate_pointer_integration.py` |
| T5 | Integration (CLI table) | yes | `check --recompute` names the pointer when it differs; not when it agrees; nothing changes without `--recompute` (R3.3) | `tests/test_gate_pointer_integration.py` |
| T6 | End-to-end (stop hook) | yes | the gate script as a subprocess against the real CLI on `PATH`, service routing off: the ticket's state exits 0; the item at `design` exits 2 with `design.md` in stderr | `tests/test_gate_pointer_integration.py` |
| T7 | Negative control | yes | T1, T3–T6 on the unfixed source (tests kept, source stashed): the new cases fail, T6's reproduction among them | the three modules |
| T8 | Manual reproduction | yes | the bugfix's console session before and after the fix | a scratch checkout |
| T9 | Regression (full suite) | yes | green from `cli/`, CI's command | `make test` |
| T10 | Static (lint, format, types, markdown, config) | yes | green | `make lint format-check typecheck validate` |
| T11 | Contract (OpenAPI) | yes | the served surface still equals the authored contract; only a description changed | `tests/test_api_contract_parity.py` (inside T9) |
| T12 | Performance | n/a: one list comprehension over ~20 nodes per stop | | |
| T13 | UI / visual | n/a: nothing rendered by the UI changes | | |

## Scenarios & requirement trace

| Requirement | Rows |
|---|---|
| R1.1–R1.3 | T1, T4, T6 |
| R2.1–R2.3 | T1, T2 |
| R3.1–R3.4 | T3, T5, T11 |

## Verification environment

- Python 3.11, `uv` 0.12, dependencies from `uv sync` against the committed `uv.lock`.
- `THE_LOOP_SERVICE_LOCAL=1` for every CLI invocation under test (the suite's autouse
  fixture; set explicitly for T6's subprocess), so no control-plane service starts.

## Activities

- [x] T8 — reproduce on the unfixed tree
- [x] T7 — negative control
- [x] T1–T6 — targeted modules
- [x] T9 — full suite from `cli/`
- [x] T10 — static checks
- [x] T8 — reproduction after the fix
