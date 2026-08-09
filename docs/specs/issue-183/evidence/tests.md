# Evidence — tests (issue-183)

> **Re-run after the PR #184 review round**, in which the outer loop's surface moved from a
> harness-config key to a per-work-item declaration at `phase-selection`. The red section
> below is the original transition (the mechanisms did not exist); the green figures are the
> re-run of the whole matrix against what shipped.

Committed output of the testing plan's activities. Run from the repository root against
the checked-in tree; no network, no credentials, nothing to redact (the only external
names in this file are the fixture repositories `octo/app`, `octo/infra`, `other/repo`,
which are invented).

## Red — before the mechanisms existed (T1, T2, T8)

The source files were reverted to `HEAD` with the new tests in place, so the failures
below are the tests failing for the absence of the behaviour rather than for a mistake:

```console
$ git checkout -- <the twelve changed source files>
$ uv run --directory cli pytest -q --continue-on-collection-errors \
    tests/test_graph_loops.py tests/test_graph_multirepo_integration.py \
    tests/test_core_graphs.py tests/test_routing.py tests/test_harness_config.py

E       AssertionError: '## What the CLI reads from it' in docs/config/harness-config.md documents keys the CLI no longer reads: ticketing.github, workflow.outerLoop.surface
E       assert not ['ticketing.github', 'workflow.outerLoop.surface']

tests/test_harness_config.py:123: AssertionError
=========================== short test summary info ============================
FAILED tests/test_graph_multirepo_integration.py::test_a_cross_repo_pull_request_routes_to_the_work_item
FAILED tests/test_graph_multirepo_integration.py::test_the_inner_loop_of_a_foreign_pr_lands_under_the_origin_spec_chain
FAILED tests/test_graph_multirepo_integration.py::test_two_repositories_share_a_pr_number_without_sharing_a_loop
FAILED tests/test_graph_multirepo_integration.py::test_the_outer_gate_holds_until_every_declared_repository_finishes
FAILED tests/test_graph_multirepo_integration.py::test_the_origin_repos_config_reaches_the_gate
FAILED tests/test_core_graphs.py::test_pr_repo_without_a_pr_is_refused - Type...
FAILED tests/test_core_graphs.py::test_a_hostile_pr_repo_argument_is_refused[../../etc]
FAILED tests/test_core_graphs.py::test_a_hostile_pr_repo_argument_is_refused[a//b]
FAILED tests/test_core_graphs.py::test_a_hostile_pr_repo_argument_is_refused[octo]
FAILED tests/test_core_graphs.py::test_a_hostile_pr_repo_argument_is_refused[a/../b]
FAILED tests/test_core_graphs.py::test_a_valid_pr_repo_selects_that_repositorys_inner_loop
FAILED tests/test_routing.py::test_router_routes_a_cross_repo_closing_reference_to_that_repository[Closes other/repo#15]
FAILED tests/test_routing.py::test_router_routes_a_cross_repo_closing_reference_to_that_repository[Closes https://github.com/other/repo/issues/15]
FAILED tests/test_routing.py::test_router_reads_a_closing_reference_that_names_its_own_repository
FAILED tests/test_harness_config.py::test_h4_every_documented_key_is_still_read
15 failed, 128 passed, 1 error in 2.12s
```

`tests/test_graph_loops.py` is the collection **error**: with `HEAD`'s
`graph/hooks/loops.py`, `declared_repos` and `repo_state_key` do not exist to import —

```console
E   ImportError: cannot import name 'declared_repos' from 'the_loop.graph.hooks.loops'
```

Each red maps to the mechanism that answers it:

| Red | Mechanism | Requirement |
|---|---|---|
| `test_graph_loops.py` import error, then its 18 multi-repo cases | `repo_state_key`, the repo-qualified `inner_loop_state_dir`, `declared_repos`, the widened `await_inner_loops` | R1.3, R1.4, R1.6, R4.1–R4.4 |
| `test_core_graphs.py::…pr_repo…` | `pr_repo` on the core verbs, refused without `pr` and validated at the boundary | R1.3, abuse case 2 |
| `test_routing.py::…cross_repo…` | `linked_work_items` returning refs, honouring a qualified reference | R1.5 |
| `test_harness_config.py::test_h4…` | the `READS` rows for `workflow.outerLoop.surface` and `ticketing.github` | R2.1 |
| `test_graph_multirepo_integration.py` (all five) | all of the above, end to end | R1.1–R1.5, R4.1, R4.2 |

## Green — T1 (unit) and the whole suite

```console
$ uv run --directory cli pytest -q
1524 passed, 1 skipped in 51.63s
```

The one skip is pre-existing and unrelated (it predates this work item). One flake worth
recording rather than smoothing over: an earlier full run had
`tests/test_tmux_runner_integration.py::test_legacy_record_without_a_tmux_target_heals_via_respawn`
fail once — a test this work item does not touch, which passed in isolation and on the
full re-run above.

## Green — T2 (integration scenarios)

```console
$ uv run --directory cli pytest -q tests/test_graph_multirepo_integration.py
6 passed in 1.23s
```

Gherkin-documented, each with a `Requirement:` link:

- `Scenario: a pull request in a contributing repository reaches its work item`
- `Scenario: a contributing repository's pull request walks its own inner loop`
- `Scenario: pull request #7 exists in both repositories`
- `Scenario: the work item waits at implementation for all its repositories`

plus two without a `Scenario:` heading (the origin-config read, and the abuse case that a
cross-repo link does not arm a work item).

## Green — T8 (security / abuse cases)

```console
$ uv run --directory cli pytest -q -k "traversal or pr_repo or unarmed or declared"
68 passed, 1457 deselected in 2.77s
```

Covering: `../../etc`, `a/../b`, `a//b`, `octo`, `""`, `octo/repo/../..`, `a\..\b` and
`octo/re po` rejected by `repo_state_key`; the same values refused through
`--pr-repo`/`core.graphs`; a cross-repo link into an unstarted work item writing no state;
and a declared repository with no inner loop holding the gate.

## Green — T10 (migration / upgrade)

```console
$ uv run --directory cli pytest -q -k "back_compat or default"
55 passed, 1470 deselected in 2.49s
```

`test_the_origin_repos_layout_is_unchanged_back_compat` pins `pr-loops/pr-<n>/` for a pull
request in the origin repository, and `test_the_surface_defaults_to_the_work_item` pins
what an untouched checklist resolves to. A `graph-state.json` written before this change
carries no `surface` field, which reads as that same default.

## Green — T3 (OpenAPI contract)

```console
$ uv run --directory cli pytest -q tests/test_api_contract_parity.py
1 passed in 1.28s
```

The authored `docs/api-specs/openapi/the-loop.v1.yaml` gained an optional `prRepo` on the
five graph request bodies and on the `graphShow` query; no path, method or `operationId`
changed, which is what this assertion compares.

## Green — the surface at `phase-selection` (added in the review round)

```console
$ uv run --directory cli pytest -q -k surface
15 passed, 1510 deselected in 2.04s
```

Four of them are the gate itself (`tests/test_graph_skips.py`): the default is the work
item and the confirmation says so; ticking `outer-loop-on-pull-request` moves it; an
**unticked** surface row is neither a declared skip nor a refused phase; and the posted
checklist offers the row under its own heading.

## Green — T12 (parity: docs ↔ code ↔ schema)

```console
$ uv run --directory cli pytest -q tests/test_docs_parity.py tests/test_harness_config.py \
    tests/test_graph_parity.py tests/test_api_contract_parity.py
32 passed in 1.66s
```
