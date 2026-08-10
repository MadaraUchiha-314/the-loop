# Evidence: test runs (issue-188)

Every command below was run from the project root on the work item's branch, after the
change. Counts are from the run; nothing here is transcribed from a plan.

## Red → green (TDD, `tdd.mode: standard`)

The production change was stashed (`git stash push -- cli/the_loop
skills/the-loop/templates/execution-log.md`) and the new tests run against the unchanged
runtime, then restored and re-run. Both directions:

```text
$ uv run pytest cli/tests/test_graph_skips.py cli/tests/test_graph_state.py \
    -q -k "opt_in or design_critic or unasked"          # production change stashed
FAILED cli/tests/test_graph_skips.py::test_opt_in_is_parsed_and_implies_skippable
FAILED cli/tests/test_graph_skips.py::test_required_and_opt_in_is_a_compile_error
FAILED cli/tests/test_graph_skips.py::test_an_opt_in_node_needs_a_declared_skipped_edge
FAILED cli/tests/test_graph_skips.py::test_a_skip_set_naming_an_opt_in_node_is_a_compile_error
FAILED cli/tests/test_graph_skips.py::test_the_shipped_outer_loop_offers_the_design_critic_round
FAILED cli/tests/test_graph_skips.py::test_only_the_outer_loop_offers_an_opt_in_phase
FAILED cli/tests/test_graph_skips.py::test_an_unselected_opt_in_node_is_routed_around_with_no_declaration
FAILED cli/tests/test_graph_skips.py::test_status_reports_an_unselected_opt_in_node_as_not_selected
FAILED cli/tests/test_graph_skips.py::test_a_selected_opt_in_node_is_walked_and_gates_its_artifact
FAILED cli/tests/test_graph_skips.py::test_a_forged_opt_in_on_a_node_that_is_not_opt_in_is_inert
FAILED cli/tests/test_graph_skips.py::test_the_checklist_offers_opt_in_phases_unticked_and_described
FAILED cli/tests/test_graph_skips.py::test_ticking_an_opt_in_row_selects_it
FAILED cli/tests/test_graph_skips.py::test_leaving_an_opt_in_row_alone_does_not_select_it
FAILED cli/tests/test_graph_skips.py::test_a_reply_that_never_mentions_an_opt_in_phase_does_not_select_it
FAILED cli/tests/test_graph_skips.py::test_an_unauthorized_reply_never_selects_an_opt_in_phase
FAILED cli/tests/test_graph_skips.py::test_the_frozen_graph_distinguishes_unasked_for_from_removed
FAILED cli/tests/test_graph_skips.py::test_a_selection_cannot_add_an_opt_in_node_already_walked
FAILED cli/tests/test_graph_state.py::test_state_serialises_selected_opt_in_phases
FAILED cli/tests/test_graph_state.py::test_a_state_file_without_opt_ins_selects_nothing
19 failed, 59 deselected in 0.49s

$ git stash pop && uv run pytest … -k "opt_in or design_critic or unasked"
19 passed, 59 deselected in 0.22s
```

## T1 — unit

```text
$ uv run pytest cli/tests/test_graph_skips.py cli/tests/test_graph_model.py \
    cli/tests/test_graph_state.py -q
116 passed in 0.62s
```

## T2 — the opt-in group (integration, both directions through the loop)

```text
$ uv run pytest cli/tests/test_graph_skips.py -q -k opt_in
15 passed, 54 deselected in 0.39s
```

## T8 — security / abuse cases

```text
$ uv run pytest cli/tests/test_graph_skips.py -q \
    -k "forged_opt_in or deleting_a_selection or unauthorized_reply_never_selects_an_opt_in"
3 passed, 66 deselected in 0.05s
```

## T10 — migration (a state file that predates the node)

```text
$ uv run pytest cli/tests/test_graph_state.py -q -k "opt_ins or without_opt_ins"
2 passed, 7 deselected in 0.04s
```

## T12 — parity (graph ↔ manifest ↔ templates ↔ docs ↔ writing contract)

```text
$ uv run pytest cli/tests/test_graph_parity.py cli/tests/test_docs_parity.py \
    cli/tests/test_writing_parity.py -q
25 passed in 0.48s
```

## Full suite

```text
$ uv run pytest cli/tests -q
1650 passed, 1 skipped in 57.89s
```

The single skip is `cli/tests/test_instructions.py:149` — an unreadable-file case that
cannot be staged as root ("root reads unpermitted files anyway"), skipped on every run in
this container and unrelated to this change.
