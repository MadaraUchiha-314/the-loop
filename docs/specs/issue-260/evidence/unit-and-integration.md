# Evidence — unit and integration runs (green)

## Whole suite

```bash
make test
```

```text
2333 passed, 1 skipped in 120.95s (0:02:00)
```

The one skip is the suite's pre-existing platform skip; it is not related to this work item.

## Targeted files

```bash
uv run --project cli python -m pytest -q \
  cli/tests/test_graph_skips.py cli/tests/test_routing.py \
  cli/tests/test_graph_contribution.py cli/tests/test_webhook_routing_integration.py \
  cli/tests/test_control.py cli/tests/test_docs_parity.py \
  cli/tests/test_configschema.py cli/tests/test_config_schema_parity.py
```

```text
372 passed in 15.77s
```

## What each row of the testing plan proved

| Row | Test | Result |
|---|---|---|
| T1 | `test_the_posted_checklist_offers_a_row_per_pr_session_mode` | three rows rendered, exactly one ticked |
| T1 | `test_the_checklist_pre_ticks_the_deployments_configured_default` (5 cases) | `always`, `never`, legacy `False`, legacy `True` and a typo each pre-tick the row the daemon would actually route by |
| T1 | `test_ticking_a_pr_session_row_freezes_that_mode` | mode in the decision, in the frozen graph, in what the sink published, and named in the confirmation |
| T1 | `test_an_unchosen_or_ambiguous_answer_keeps_the_configured_default` (3 cases) | nothing ticked, an explicit untick, and two ticked all resolve to the configured value |
| T1 | `test_a_pr_session_row_is_never_read_as_a_phase` | unticked rows produce neither a skip nor a refusal |
| T1 / R1.5 | `test_the_contribution_checklist_still_asks_how_many_pr_sessions` | the rows are offered on the contribution loop, where the surface row is not |
| T2 | `test_an_unrecognised_session_per_pr_fails_closed_to_cross_repository`, `test_the_mode_answers_the_two_questions_routing_asks` (pre-existing) | the resolver answers identically from `the_loop.prsessions`; the move changed no behaviour |
| T3 | `test_a_work_items_frozen_choice_overrides_the_operators_default` (3 × 2 cases) | a frozen mode decides on a daemon configured `cross-repository`, both for a same-repository and a cross-repository pull request |
| T3 / T12 | `test_a_work_item_with_no_usable_choice_routes_by_the_configured_default` (4 cases) | absent, `"sometimes"`, `""` and `3` all fall back |
| T3 | `test_one_work_items_choice_does_not_move_another_ones` | one daemon, two work items, opposite answers |
| T3 | `test_delivery_status_resolves_through_the_work_items_own_choice` | a delivery recorded on the work item's session under a frozen `never` reports `done` when the retry path asks about the **pull request's** ref |
| T4 | `test_the_work_items_own_selection_decides_which_session_a_pr_talks_to` (2 cases) | through a real signed webhook POST: unfrozen → the pull request's own conversation, frozen `never` → the work item's, no spawn either way |
| T10 | `test_an_unauthorized_ticker_cannot_freeze_a_mode` | the gate stays `wait`, no decision recorded |
| T10 | `test_a_token_outside_the_vocabulary_is_ignored_not_obeyed` | `pr-sessions-sometimes` neither obeyed nor refused |
| T10 | `test_a_work_item_with_no_usable_choice_routes_by_the_configured_default` | a hand-edited portable record cannot reach `TmuxConfig` |
| T14 | `test_docs_parity.py`, `test_config_schema_parity.py` | the schema is unchanged in shape and its two copies stay byte-identical; the documented option still matches it |

## Regression surface

No existing test was changed to accommodate this work item. Three test helpers were touched:

- `cli/tests/test_routing.py::_endpoint_ref_for` gained `frozen=` and `ref=`, and now points
  `portable_dir` at `tmp_path` — previously it inherited `RoutingConfig`'s default, which is
  this repository's own `.the-loop/portable`.
- `cli/tests/test_webhook_routing_integration.py::pr_comment_payload` gained `repo=`, so a
  comment can arrive on a pull request in another repository.
- `cli/tests/test_graph_skips.py::_selecting_with` is new — a `selecting` runtime with
  CLI-config-derived hook config.
