# Evidence — the red run

The TDD record for issue-260: the new tests, run against the **unchanged** production code.
Captured by stashing `cli/the_loop/` (production only — the tests stay) and running the four
affected files, then restoring.

```bash
git stash push -- cli/the_loop
uv run --project cli python -m pytest -q \
  cli/tests/test_graph_skips.py cli/tests/test_routing.py \
  cli/tests/test_graph_contribution.py cli/tests/test_webhook_routing_integration.py
git stash pop
```

```text
FAILED cli/tests/test_graph_skips.py::test_the_posted_checklist_offers_a_row_per_pr_session_mode
FAILED cli/tests/test_graph_skips.py::test_the_checklist_pre_ticks_the_deployments_configured_default[always-pr-sessions-always]
FAILED cli/tests/test_graph_skips.py::test_the_checklist_pre_ticks_the_deployments_configured_default[never-pr-sessions-never]
FAILED cli/tests/test_graph_skips.py::test_the_checklist_pre_ticks_the_deployments_configured_default[False-pr-sessions-never]
FAILED cli/tests/test_graph_skips.py::test_the_checklist_pre_ticks_the_deployments_configured_default[True-pr-sessions-cross-repository]
FAILED cli/tests/test_graph_skips.py::test_the_checklist_pre_ticks_the_deployments_configured_default[sometimes-pr-sessions-cross-repository]
FAILED cli/tests/test_graph_skips.py::test_ticking_a_pr_session_row_freezes_that_mode
FAILED cli/tests/test_graph_skips.py::test_an_unchosen_or_ambiguous_answer_keeps_the_configured_default[the-loop execute]
FAILED cli/tests/test_graph_skips.py::test_an_unchosen_or_ambiguous_answer_keeps_the_configured_default[- [ ] pr-sessions-always\nthe-loop execute]
FAILED cli/tests/test_graph_skips.py::test_an_unchosen_or_ambiguous_answer_keeps_the_configured_default[- [x] pr-sessions-always\n- [x] pr-sessions-never\nthe-loop execute]
FAILED cli/tests/test_graph_skips.py::test_a_token_outside_the_vocabulary_is_ignored_not_obeyed
FAILED cli/tests/test_routing.py::test_a_work_items_frozen_choice_overrides_the_operators_default[always-github:octo/repo#16-github:octo/other#16]
FAILED cli/tests/test_routing.py::test_a_work_items_frozen_choice_overrides_the_operators_default[never-github:octo/repo#15-github:octo/repo#15]
FAILED cli/tests/test_routing.py::test_one_work_items_choice_does_not_move_another_ones
FAILED cli/tests/test_routing.py::test_delivery_status_resolves_through_the_work_items_own_choice
FAILED cli/tests/test_graph_contribution.py::test_the_contribution_checklist_still_asks_how_many_pr_sessions
FAILED cli/tests/test_webhook_routing_integration.py::test_the_work_items_own_selection_decides_which_session_a_pr_talks_to[never-github:octo/repo#15]
17 failed, 274 passed in 14.64s
```

## Reading the red

| Failure group | Why it fails before the change |
|---|---|
| `test_graph_skips.py` — 11 | The checklist has no `pr-sessions-*` rows to render or parse, so nothing is rendered, nothing is frozen and `decisions["phase-selection"]` carries no `sessionPerPr`. |
| `test_routing.py::…overrides_the_operators_default` — 2 of 3 | `_endpoint_for` reads `self.config.tmux` only, so a frozen `always` still collapses a same-repository pull request and a frozen `never` still splits a cross-repository one. The third case (`frozen == "cross-repository"`) passes red **by construction** — it agrees with the configured default, which is the point of the row. |
| `test_routing.py::…does_not_move_another_ones` | Same cause, both directions at once. |
| `test_routing.py::…delivery_status…` | `delivery_status` passed the operator's `splits_pull_requests`, so the PR's linked-but-unspawned endpoint was resolved instead of the session that recorded the delivery: `unhandled` for a delivery that succeeded. |
| `test_graph_contribution.py` | The contribution loop's checklist carries no rows either. |
| `test_webhook_routing_integration.py` — 1 of 2 | The `frozen=None` case is the unchanged behaviour and passes red on purpose; the `never` case routes to the pull request's own conversation because nothing reads the work item's answer. |

Three rows deliberately **pass** red — `frozen=None`, `frozen="sometimes"` and the
integration test's unfrozen case. They assert the fallback, which is the requirement that
nothing changes for a work item that never answered (R2.2, R2.3, R3.4); a fallback test that
failed before the change would be asserting the wrong thing.

## Order of work

The production edits were drafted before the tests were written and were reverted to produce
this capture, rather than the tests being authored first against an untouched tree. The
failure set is genuine — it is the real behaviour of `main` plus these tests — but the
sequence is a deviation from `tdd.mode: standard` and is recorded as one in
[`execution-log.md`](../execution-log.md) § Deviations.
