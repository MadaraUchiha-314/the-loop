# Evidence — units (T1, T2, T4), abuse cases (T10) and migration (T12)

Work item: issue-199 · captured 2026-08-10 · no network, no credentials.

## T1 / T2 / T10 — `uv run --project cli python -m pytest -q cli/tests/test_graph_contribution.py`

```text
..............................................                           [100%]
46 passed in 0.63s
```

The ten cases this work item added or relies on, by name:

```text
tests/test_graph_contribution.py::test_the_contribution_checklist_offers_no_surface_row
tests/test_graph_contribution.py::test_the_outer_loops_checklist_still_asks_the_question
tests/test_graph_contribution.py::test_a_ticked_surface_row_in_a_contributions_reply_changes_nothing
tests/test_graph_contribution.py::test_the_arming_comment_reaches_the_goal_gate_at_spawn
tests/test_graph_contribution.py::test_a_spawn_with_no_goal_parks_the_gate_with_its_reason
tests/test_graph_contribution.py::test_a_respawn_re_evaluates_nothing
tests/test_graph_contribution.py::test_an_unauthorized_goal_is_not_read
tests/test_graph_contribution.py::test_a_self_authored_goal_is_not_read
tests/test_graph_contribution.py::test_an_outage_reads_as_no_goal_never_a_guess
tests/test_graph_contribution.py::TestContributionWalk::test_goal_then_selection_release_only_on_authorized_input
```

### T2 — the spawn rows on their own

```text
$ uv run --project cli python -m pytest -q cli/tests/test_graph_contribution.py -k spawn
....                                                                     [100%]
4 passed, 42 deselected in 0.14s
```

### T10 — the abuse cases

```text
$ uv run --project cli python -m pytest -q cli/tests/test_graph_contribution.py \
      -k "unauthorized or surface"
...                                                                      [100%]
3 passed, 43 deselected in 0.09s
```

- **Abuse 1** (an unauthorized user answers the gate) —
  `test_an_unauthorized_goal_is_not_read`, plus `test_a_self_authored_goal_is_not_read`
  for the harness answering its own gate. Both pre-date this change and are re-run
  because `on_spawn` now reaches the same gate: the new caller must not widen who may
  answer it.
- **Abuse 2** (an injected `outer-loop-on-pull-request` row makes the-loop open a pull
  request) — `test_a_ticked_surface_row_in_a_contributions_reply_changes_nothing`: the
  pointer advances on the phase selection, `state.surface` stays `""`, the frozen record
  carries `""`, no phase is declared away, and the confirmation says nothing about a
  surface.
- **Abuse 3** (a gate fault at spawn wedges the item) —
  `test_an_outage_reads_as_no_goal_never_a_guess`: an integration that raises on every
  call leaves the gate waiting rather than guessing, and `GraphLink._guarded` swallows and
  records any fault above it.

## T4 — `uv run --project cli python -m pytest -q cli/tests/test_graph_drive.py`

```text
......................                                                   [100%]
22 passed in 2.29s
```

Three cases matter here:

```text
tests/test_graph_drive.py::test_the_render_places_the_outer_loops_artifacts
tests/test_graph_drive.py::test_a_contribution_is_not_told_where_to_put_an_outer_loop
tests/test_graph_drive.py::test_a_spawn_never_evaluates_an_agent_start_node
```

The last is R2.4's guard: the fixture's graph starts at an **agent** node whose
`design.md` is deliberately absent, so an evaluation at spawn would have blocked. It is
entered, not evaluated — `parked is None`, no `last_block`, one attempt.

## T12 — migration

No persisted schema changed. `graph-state.json` keeps every field it had, and `surface`
keeps its type: a work item frozen by 9.6.0 with `surface: "work-item"` reads identically
(`test_state_loop_round_trips_and_predates_gracefully`, and the state round-trip cases in
`test_graph_state.py`, all part of T6). The only new value is the empty string, which
every reader already treated as "unset" — `Runtime._record_selected_skips` writes
`state.surface` only for a truthy value, and `graphlink._surface_line("")` has always
rendered the default.
