# Evidence — unit, integration, contract and abuse-case runs (green)

Every row of [`testing-plan.md`](../testing-plan.md) marked `yes`, executed. The same
commands CI runs (`make test` is `uv run --project cli python -m pytest -q cli`), so local
and CI are the same tool on the same tree.

## Whole suite (T1, T2, T3, T8, T10, T12)

```
$ uv run --project cli python -m pytest -q cli
........................................................................ [ 99%]
.....                                                                    [100%]
2308 passed, 1 skipped in 131.15s (0:02:11)
```

Before this work item the same suite was 2,305 passed / 1 skipped; the 28 tests added here
account for the difference, and nothing that passed before was changed to keep passing.

## The files this work item touches

```
$ uv run --project cli python -m pytest -q \
    cli/tests/test_routing.py cli/tests/test_workspace.py \
    cli/tests/test_configschema.py cli/tests/test_config_schema_parity.py \
    cli/tests/test_webhook_routing_integration.py cli/tests/test_docs_parity.py
........................................................................ [ 31%]
........................................................................ [ 62%]
........................................................................ [ 93%]
..............                                                           [100%]
230 passed in 16.71s
```

## T1 + T8 + T10 — the mode table, the routing rule, back-compatibility

```
$ uv run --project cli python -m pytest cli/tests/test_routing.py \
    -k "session_per_pr or operator_chooses or mode_answers or always_still" -v
cli/tests/test_routing.py::test_session_per_pr_resolves_to_one_of_three_modes[configured0-cross-repository]
cli/tests/test_routing.py::test_session_per_pr_resolves_to_one_of_three_modes[configured1-cross-repository]
cli/tests/test_routing.py::test_session_per_pr_resolves_to_one_of_three_modes[configured2-never]
cli/tests/test_routing.py::test_session_per_pr_resolves_to_one_of_three_modes[configured3-never]
cli/tests/test_routing.py::test_session_per_pr_resolves_to_one_of_three_modes[configured4-cross-repository]
cli/tests/test_routing.py::test_session_per_pr_resolves_to_one_of_three_modes[configured5-always]
cli/tests/test_routing.py::test_an_unrecognised_session_per_pr_fails_closed_to_cross_repository[sometimes]
cli/tests/test_routing.py::test_an_unrecognised_session_per_pr_fails_closed_to_cross_repository[ALWAYS]
cli/tests/test_routing.py::test_an_unrecognised_session_per_pr_fails_closed_to_cross_repository[]
cli/tests/test_routing.py::test_an_unrecognised_session_per_pr_fails_closed_to_cross_repository[3]
cli/tests/test_routing.py::test_an_unrecognised_session_per_pr_fails_closed_to_cross_repository[bad4]
cli/tests/test_routing.py::test_the_mode_answers_the_two_questions_routing_asks[never-False-False]
cli/tests/test_routing.py::test_the_mode_answers_the_two_questions_routing_asks[cross-repository-True-False]
cli/tests/test_routing.py::test_the_mode_answers_the_two_questions_routing_asks[always-True-True]
cli/tests/test_routing.py::test_the_operator_chooses_which_pull_requests_get_their_own_session[never-github:octo/repo#15-github:octo/repo#15]
cli/tests/test_routing.py::test_the_operator_chooses_which_pull_requests_get_their_own_session[cross-repository-github:octo/repo#15-github:octo/other#16]
cli/tests/test_routing.py::test_the_operator_chooses_which_pull_requests_get_their_own_session[always-github:octo/repo#16-github:octo/other#16]
cli/tests/test_routing.py::test_always_still_declines_the_session_when_there_is_no_checkout_for_it

18 passed, 111 deselected
```

The `[configured1-cross-repository]` and `[configured2-never]` cases are R3.1 and R3.2 —
the two booleans an existing config file carries, resolving to the modes they mean today.

## T1 + T2 + T8 — the branch requirement, and `always` end to end

```
$ uv run --project cli python -m pytest cli/tests/test_workspace.py \
    -k "require_branch or always or shell or clone_strategy_can_hold" -v
cli/tests/test_workspace.py::test_require_branch_refuses_a_worktree_that_is_not_on_the_branch
cli/tests/test_workspace.py::test_require_branch_refuses_when_a_sibling_worktree_already_holds_the_branch
cli/tests/test_workspace.py::test_clone_strategy_require_branch_refuses_to_stay_on_the_default_branch
cli/tests/test_workspace.py::test_clone_strategy_can_hold_a_branch_a_sibling_worktree_already_has
cli/tests/test_workspace.py::test_git_is_invoked_without_a_shell
cli/tests/test_workspace.py::test_always_gives_a_same_repository_pull_request_its_own_clone_and_session
cli/tests/test_workspace.py::test_always_declines_to_one_session_when_the_branch_cannot_be_held_twice

7 passed, 35 deselected
```

`test_require_branch_refuses_when_a_sibling_worktree_already_holds_the_branch` is the one
that matters most: it asserts the *degradation* first — a second worktree asking for a
branch a sibling holds lands on `main` at a different path — and only then that
`require_branch=True` refuses it. That degraded tree passing the shared-tree guard is the
failure mode `always` would otherwise have shipped with.

## T3 — the schema contract

```
$ uv run --project cli python -m pytest cli/tests/test_configschema.py -k session_per_pr -v
cli/tests/test_configschema.py::test_session_per_pr_accepts_both_booleans_and_all_three_modes[True]
cli/tests/test_configschema.py::test_session_per_pr_accepts_both_booleans_and_all_three_modes[False]
cli/tests/test_configschema.py::test_session_per_pr_accepts_both_booleans_and_all_three_modes[never]
cli/tests/test_configschema.py::test_session_per_pr_accepts_both_booleans_and_all_three_modes[cross-repository]
cli/tests/test_configschema.py::test_session_per_pr_accepts_both_booleans_and_all_three_modes[always]

5 passed
```

The rejected values (`"sometimes"`, `1`) are in the shared `INVALID` corpus, so they are
also checked by `test_this_validator_agrees_with_jsonschema` — the hand-written validator
and the real `jsonschema` return the same verdict on all five accepted and both rejected
values.

Nothing in this capture contains a token, a cookie, personal data or an internal hostname:
it is pytest node ids and counts over paths inside the repository and pytest's `tmp_path`.
