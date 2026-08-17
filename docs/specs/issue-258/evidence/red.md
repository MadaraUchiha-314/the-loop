# Evidence — the red run (TDD, `tdd.mode: standard`)

Captured **before** a single production line changed, on the commit that adds the tests
only. Every failure below is a test asserting behaviour issue-258 asks for and the-loop
does not yet have. Two independent red roots, exactly as `tasks.md` §DAG describes: the
config/routing chain and the workspace chain.

Command:

```
uv run --project cli python -m pytest -q cli/tests/test_routing.py cli/tests/test_workspace.py
uv run --project cli python -m pytest -q cli/tests/test_configschema.py
```

## What is red, and why

| Test | Fails because |
|---|---|
| `test_session_per_pr_resolves_to_one_of_three_modes` (6 cases) | `TmuxConfig.session_per_pr` is a `bool`; there is no mode to resolve to |
| `test_an_unrecognised_session_per_pr_fails_closed_to_cross_repository` (6 cases) | `bool("sometimes")` is `True` — an unrecognised value silently becomes the splitting choice, with no warning |
| `test_the_mode_answers_the_two_questions_routing_asks` (3 cases) | `splits_pull_requests` / `splits_same_repository` do not exist |
| `test_the_operator_chooses_which_pull_requests_get_their_own_session[never]` | `TmuxConfig(session_per_pr="never")` is truthy, so a cross-repository PR splits when the operator said it should not |
| `test_the_operator_chooses_which_pull_requests_get_their_own_session[always]` | issue-253's same-repository collapse is unconditional |
| `test_require_branch_refuses_*` (3 tests) | `Workspace.prepare` / `ensure_worktree` take no `require_branch` |
| `test_clone_strategy_can_hold_a_branch_a_sibling_worktree_already_has` | same — the keyword does not exist |
| `test_git_is_invoked_without_a_shell` | same — `TypeError: unexpected keyword argument 'require_branch'` |
| `test_always_gives_a_same_repository_pull_request_its_own_clone_and_session` | no second session is spawned: the collapse is a rule |
| `test_session_per_pr_accepts_both_booleans_and_all_three_modes` (3 of 5) | the schema leaf is `{"type": "boolean"}` |
| `test_valid_documents_report_nothing[routing]`, `test_this_validator_agrees_with_jsonschema` | the same schema leaf, through the corpus and the differential check |

The `cross-repository` rows of the routing table **pass** while red — they assert today's
behaviour, and they are in the parametrization to prove the default did not move.

## Raw output

```text
### routing + workspace

cli/tests/test_workspace.py:879: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  the-loop.graph:graphlink.py:682 /tmp/pytest-of-root/pytest-1/test_always_gives_a_same_repos0/root/.work-items/github-octo-repo-15/github.com/octo/repo is not a checkout of octo/repo, so a work item directory there belongs to a different project; not contexting a graph in it
WARNING  the-loop.graph:graphlink.py:682 /tmp/pytest-of-root/pytest-1/test_always_gives_a_same_repos0/root/.work-items/github-octo-repo-15/github.com/octo/repo is not a checkout of octo/repo, so a work item directory there belongs to a different project; not advanceing a graph in it
=========================== short test summary info ============================
FAILED cli/tests/test_routing.py::test_session_per_pr_resolves_to_one_of_three_modes[configured0-cross-repository]
FAILED cli/tests/test_routing.py::test_session_per_pr_resolves_to_one_of_three_modes[configured1-cross-repository]
FAILED cli/tests/test_routing.py::test_session_per_pr_resolves_to_one_of_three_modes[configured2-never]
FAILED cli/tests/test_routing.py::test_session_per_pr_resolves_to_one_of_three_modes[configured3-never]
FAILED cli/tests/test_routing.py::test_session_per_pr_resolves_to_one_of_three_modes[configured4-cross-repository]
FAILED cli/tests/test_routing.py::test_session_per_pr_resolves_to_one_of_three_modes[configured5-always]
FAILED cli/tests/test_routing.py::test_an_unrecognised_session_per_pr_fails_closed_to_cross_repository[sometimes]
FAILED cli/tests/test_routing.py::test_an_unrecognised_session_per_pr_fails_closed_to_cross_repository[ALWAYS]
FAILED cli/tests/test_routing.py::test_an_unrecognised_session_per_pr_fails_closed_to_cross_repository[]
FAILED cli/tests/test_routing.py::test_an_unrecognised_session_per_pr_fails_closed_to_cross_repository[3]
FAILED cli/tests/test_routing.py::test_an_unrecognised_session_per_pr_fails_closed_to_cross_repository[None]
FAILED cli/tests/test_routing.py::test_an_unrecognised_session_per_pr_fails_closed_to_cross_repository[bad5]
FAILED cli/tests/test_routing.py::test_the_mode_answers_the_two_questions_routing_asks[never-False-False]
FAILED cli/tests/test_routing.py::test_the_mode_answers_the_two_questions_routing_asks[cross-repository-True-False]
FAILED cli/tests/test_routing.py::test_the_mode_answers_the_two_questions_routing_asks[always-True-True]
FAILED cli/tests/test_routing.py::test_the_operator_chooses_which_pull_requests_get_their_own_session[never-github:octo/repo#15-github:octo/repo#15]
FAILED cli/tests/test_routing.py::test_the_operator_chooses_which_pull_requests_get_their_own_session[always-github:octo/repo#16-github:octo/other#16]
FAILED cli/tests/test_workspace.py::test_require_branch_refuses_a_worktree_that_is_not_on_the_branch
FAILED cli/tests/test_workspace.py::test_require_branch_refuses_when_a_sibling_worktree_already_holds_the_branch
FAILED cli/tests/test_workspace.py::test_clone_strategy_require_branch_refuses_to_stay_on_the_default_branch
FAILED cli/tests/test_workspace.py::test_clone_strategy_can_hold_a_branch_a_sibling_worktree_already_has
FAILED cli/tests/test_workspace.py::test_git_is_invoked_without_a_shell - Typ...
FAILED cli/tests/test_workspace.py::test_always_gives_a_same_repository_pull_request_its_own_clone_and_session
23 failed, 149 passed in 9.38s
cli/tests/test_configschema.py:183: AssertionError
=========================== short test summary info ============================
FAILED cli/tests/test_configschema.py::test_valid_documents_report_nothing[['routing']2]
FAILED cli/tests/test_configschema.py::test_session_per_pr_accepts_both_booleans_and_all_three_modes[never]
FAILED cli/tests/test_configschema.py::test_session_per_pr_accepts_both_booleans_and_all_three_modes[cross-repository]
FAILED cli/tests/test_configschema.py::test_session_per_pr_accepts_both_booleans_and_all_three_modes[always]
FAILED cli/tests/test_configschema.py::test_this_validator_agrees_with_jsonschema
5 failed, 24 passed in 0.66s
```

**28 failed** across the three files (23 + 5), 173 passed. No secret, token, hostname or
personal datum appears in this capture: it is pytest node ids and assertion text over
paths inside the repository and pytest's `tmp_path`.
