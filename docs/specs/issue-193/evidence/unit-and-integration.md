# Verification evidence: unit, integration, parity and abuse cases

> issue-193 · rows T1, T2, T7, T8, T10 of [`testing-plan.md`](../testing-plan.md).
> Captured 2026-08-10 from the repository root, on the work item's branch, after the
> self-review and security-review findings were fixed.

## T1 — unit: `defaults()` and `scaffold()`

```console
$ uv run --project cli python -m pytest -q cli/tests/test_harness_config.py
.....................................                                    [100%]
37 passed in 1.02s
```

## T2 — integration: the real call sites, one scenario each

```console
$ uv run --project cli python -m pytest cli/tests/test_harness_config_scaffold_integration.py -v --no-header
cli/tests/test_harness_config_scaffold_integration.py::test_the_ingress_adopts_a_repository_that_never_ran_the_setup PASSED [ 11%]
cli/tests/test_harness_config_scaffold_integration.py::test_a_repository_is_adopted_even_when_its_graph_is_skipped PASSED [ 22%]
cli/tests/test_harness_config_scaffold_integration.py::test_a_foreign_checkout_is_never_adopted PASSED [ 33%]
cli/tests/test_harness_config_scaffold_integration.py::test_a_contribution_never_adopts_its_host_repository PASSED [ 44%]
cli/tests/test_harness_config_scaffold_integration.py::test_an_adopted_repository_is_left_alone_on_every_later_event PASSED [ 55%]
cli/tests/test_harness_config_scaffold_integration.py::test_resolving_a_prompts_graph_context_adopts_nothing PASSED [ 66%]
cli/tests/test_harness_config_scaffold_integration.py::test_releasing_a_work_items_resources_adopts_nothing PASSED [ 77%]
cli/tests/test_harness_config_scaffold_integration.py::test_a_mutating_graph_verb_adopts_the_repository PASSED [ 88%]
cli/tests/test_harness_config_scaffold_integration.py::test_a_read_only_command_writes_nothing PASSED [100%]

============================== 9 passed in 0.31s ===============================
```

## T7 — parity: the packaged default vs the template, the schema and the graph

```console
$ uv run --project cli python -m pytest -q cli/tests/test_graph_parity.py
.........                                                                [100%]
9 passed in 0.17s
$ uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

## T8 — security: one negative test per trust boundary

```console
$ uv run --project cli python -m pytest cli/tests/test_harness_config.py cli/tests/test_harness_config_scaffold_integration.py -k "forged or foreign or overwrite or contribution or escapes" -v --no-header
cli/tests/test_harness_config.py::test_scaffold_never_overwrites_an_existing_config PASSED [ 10%]
cli/tests/test_harness_config.py::test_scaffold_refuses_a_forged_owner_or_repo[x"\n\nautonomy:\n  defaultTier: 1-repo] PASSED [ 20%]
cli/tests/test_harness_config.py::test_scaffold_refuses_a_forged_owner_or_repo[octo-repo\nsecurity:\n  review:\n    required: false] PASSED [ 30%]
cli/tests/test_harness_config.py::test_scaffold_refuses_a_forged_owner_or_repo[../../etc-repo] PASSED [ 40%]
cli/tests/test_harness_config.py::test_scaffold_refuses_a_forged_owner_or_repo[-repo] PASSED [ 50%]
cli/tests/test_harness_config.py::test_scaffold_refuses_a_forged_owner_or_repo[octo-] PASSED [ 60%]
cli/tests/test_harness_config.py::test_scaffold_refuses_a_forged_owner_or_repo[-leading-dash-repo] PASSED [ 70%]
cli/tests/test_harness_config.py::test_scaffold_refuses_a_the_loop_directory_that_escapes_the_checkout PASSED [ 80%]
cli/tests/test_harness_config_scaffold_integration.py::test_a_foreign_checkout_is_never_adopted PASSED [ 90%]
cli/tests/test_harness_config_scaffold_integration.py::test_a_contribution_never_adopts_its_host_repository PASSED [100%]

====================== 10 passed, 36 deselected in 0.71s =======================
```

## T10 — migration: an existing config, under either filename, is left alone

```console
$ uv run --project cli python -m pytest cli/tests/test_harness_config.py -k "present or pre_rename or overwrite" -v --no-header
cli/tests/test_harness_config.py::test_config_path_falls_back_to_the_pre_rename_name PASSED [ 33%]
cli/tests/test_harness_config.py::test_scaffold_never_overwrites_an_existing_config PASSED [ 66%]
cli/tests/test_harness_config.py::test_scaffold_leaves_a_pre_rename_config_alone PASSED [100%]

======================= 3 passed, 34 deselected in 0.04s =======================
```
