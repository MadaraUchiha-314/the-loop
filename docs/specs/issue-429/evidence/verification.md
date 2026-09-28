---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#429"
---

# Verification: the stop gate blocks on a node the work item never entered

> The `verification` node's captured output, one section per row of
> [`testing-plan.md`](../testing-plan.md). Environment: Python 3.11, `uv` 0.12.19,
> `uv sync` against the committed `uv.lock`, `THE_LOOP_SERVICE_LOCAL=1` for CLI runs.

## Verification results

| Row | Command | Outcome |
|-----|---------|---------|
| T8 (before) | the bugfix's console session on `48cb8e6` | `check` → `ok (at phase-selection)`; `check --recompute` → `UNMET (at design)`; gate → exit 2, demands `design.md` |
| T7 | the three modules on the unfixed source (tests kept, source stashed) | **13 failed**, 58 passed. Every new pointer case fails, the T6 subprocess reproduction among them; the pinned key set fails on the missing `pointer` |
| T1, T2 | `tests/test_harness_gate.py` | green; every pre-existing case unchanged |
| T3–T6 | `tests/test_gate_pointer_integration.py`, `tests/test_core_graphs.py` | green |
| T1–T6, T11 | the five modules together, final tree | 81 passed |
| T9 | `cd cli && uv run python -m pytest -q` (CI's command) | **4684 passed, 1 skipped** in 198.77s; working tree clean of test writes afterwards |
| T10 | `ruff format --check`, `ruff check`, `pyright cli`, `scripts/validate_config.py`, `markdownlint-cli2 "**/*.md"` | all green: 0 pyright errors, 0 markdown errors, both configs valid |
| T8 (after) | the same session, fixed source | gate → exit 0; `check --recompute` → `state: … (pointer at phase-selection; position derived from the artifacts)`; JSON carries `"pointer": "phase-selection"` |

## T8: before and after

Before (unfixed):

```text
$ the-loop check issue-1
issue-1: ok (at phase-selection)
$ the-loop check issue-1 --recompute
issue-1: UNMET (at design)
  BLOCK  design
         · required artifact is missing (docs/specs/issue-1/design.md)
$ THE_LOOP_WORK_ITEM=issue-1 python3 hooks/the-loop-gate.py claude; echo "exit=$?"
the-loop: this step is not complete.
  · required artifact is missing (docs/specs/issue-1/design.md)

Fix the above, then finish. (attempt 1/3)
exit=2
```

After:

```text
$ the-loop check issue-1 --recompute | head -2
issue-1: UNMET (at design)
  state: …/docs/specs/issue-1/work-item-state.json (pointer at phase-selection; position derived from the artifacts)
$ the-loop check issue-1 --recompute --format json | grep -E '"(currentNode|pointer)"'
  "currentNode": "design",
  "pointer": "phase-selection"
$ THE_LOOP_WORK_ITEM=issue-1 python3 hooks/the-loop-gate.py claude; echo "exit=$?"
exit=0
```

## T7: negative control

```text
FAILED tests/test_harness_gate.py::TestThePointerBoundsTheGate::test_a_node_the_item_never_entered_does_not_block
FAILED tests/test_harness_gate.py::TestThePointerBoundsTheGate::test_a_satisfied_walk_up_to_the_pointer_blocks_nothing
FAILED tests/test_harness_gate.py::TestThePointerBoundsTheGate::test_no_recorded_position_is_inconclusive[]
FAILED tests/test_harness_gate.py::TestThePointerBoundsTheGate::test_no_recorded_position_is_inconclusive[None]
FAILED tests/test_harness_gate.py::TestThePointerBoundsTheGate::test_a_pointer_naming_no_node_in_the_report_is_inconclusive
FAILED tests/test_gate_pointer_integration.py::TestTheReportCarriesThePointer::test_recompute_reports_both_positions
FAILED tests/test_gate_pointer_integration.py::TestTheReportCarriesThePointer::test_without_recompute_the_pointer_is_the_current_node
FAILED tests/test_gate_pointer_integration.py::TestTheReportCarriesThePointer::test_no_state_file_is_no_pointer[False]
FAILED tests/test_gate_pointer_integration.py::TestTheReportCarriesThePointer::test_no_state_file_is_no_pointer[True]
FAILED tests/test_gate_pointer_integration.py::TestTheGateOnARealReport::test_a_parked_item_is_not_told_to_write_a_later_phase
FAILED tests/test_gate_pointer_integration.py::TestTheCheckTableSaysBoth::test_a_derived_position_ahead_of_the_pointer_is_named
FAILED tests/test_gate_pointer_integration.py::TestTheStopHookEndToEnd::test_the_ticket_reproduction_lets_the_turn_end
FAILED tests/test_core_graphs.py::test_a_resolving_repo_keeps_exactly_the_keys_it_always_had
13 failed, 58 passed in 1.58s
```

These cases pass on the unfixed tree too, and they are meant to. They pin behaviour the
fix must keep:

- blocking at the pointer;
- a broken node behind the pointer;
- `wait` before the pointer;
- an unresolved `currentNode`.

## Note: a stale service during verification

The first "after" run went through a control-plane service that had auto-started on the
pre-change code. It answered without `pointer`, and the gate took the R2.3 fallback
(the old behaviour) instead of crashing. Stopping the service fixed it. The operator
note in [`reviewer-briefing.md`](reviewer-briefing.md) records this.
