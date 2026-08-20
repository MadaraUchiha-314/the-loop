# Red run — the tests that motivate the change (issue-273)

Captured with the production change (`cli/the_loop/graphlink.py`) stashed and the test
changes in place, so every failure below is the reported bug rather than a missing symbol.

## Command

```console
$ git stash push cli/the_loop/graphlink.py
$ uv run pytest -q -p no:randomly \
    cli/tests/test_graphlink.py cli/tests/test_graph_drive.py \
    cli/tests/test_graphlink_integration.py \
    cli/tests/test_harness_config_scaffold_integration.py
```

## Output

```text
=========================== short test summary info ============================
FAILED cli/tests/test_graphlink.py::test_a_work_item_with_no_spec_directory_is_still_started
FAILED cli/tests/test_graphlink.py::test_the_gate_reads_the_same_directory_the_runtime_will
FAILED cli/tests/test_graphlink.py::test_a_start_with_no_spec_directory_records_no_skip
FAILED cli/tests/test_graph_drive.py::test_a_fresh_item_reports_the_node_it_is_about_to_stand_on
FAILED cli/tests/test_graphlink_integration.py::test_a_ticket_with_no_spec_folder_is_still_held_at_phase_selection
FAILED cli/tests/test_graphlink_integration.py::test_the_gate_still_waits_for_an_authorized_human
FAILED cli/tests/test_graphlink_integration.py::test_the_spawn_prompt_of_an_unplaced_work_item_forbids_starting_a_phase
FAILED cli/tests/test_harness_config_scaffold_integration.py::test_a_repository_is_adopted_even_when_its_graph_is_skipped
8 failed, 79 passed in 18.44s
```

## What each failure says

| Test | Pre-fix assertion failure | Requirement |
|---|---|---|
| `…_is_still_started` | `runtime.started == []` — the coupling declined to start the graph | R1.1 |
| `test_the_gate_reads_the_same_directory_the_runtime_will` | `runtime.built == []` after the spawn — the exempt action never got as far as building a runtime | R1.5 |
| `…_records_no_skip` | two `graph.skipped` records (`context`, `start`), reason `no-spec-dir` — the bug's exact signature from the ticket | R1.1 |
| `…_reports_the_node_it_is_about_to_stand_on` | `context(...)` returned `None` | R2.1 |
| `…_is_still_held_at_phase_selection` | `GraphState.current_node` was `""` — no graph, no `loop:phase-selection` label, no checklist | R1.1, R1.2 |
| `test_the_gate_still_waits_for_an_authorized_human` | same: there was no graph for the unauthorized comment to fail to move | R1.3 |
| `…_forbids_starting_a_phase` | the context was `None`, so `render_graph_context` produced the empty block the auto-execute prompt shipped with | R2.1, R2.2 |
| `test_a_repository_is_adopted_even_when_its_graph_is_skipped` | no `graph-state.json` — adoption happened, the graph did not | R1.1, R1.2 |

The one new test that passes **before** the fix is deliberate:
`test_a_graph_that_has_started_reports_its_real_node` is the control for R2.3 — `pending`
must never mask a work item in flight — so it is green on both sides of the change.
