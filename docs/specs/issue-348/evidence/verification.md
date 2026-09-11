# Verification evidence — issue-348

Executed 2026-09-11 on `claude/github-issue-348-vx9u2l`, from the repository checkout with
`uv run --project cli`. No network, no GitHub call, no credential read: the receiver tests
POST into the stdlib handler with a fixture secret, and the poller tests run against a
stub `gh` on `PATH` that lists nothing.

## Red first

The new suites fail against the base commit `35a08cf`, in a worktree of that commit with
only the new test files copied in:

| Suite | Against `35a08cf` |
|---|---|
| `cli/tests/test_repositories.py` | **collection error** — `ImportError: cannot import name 'repos' from 'the_loop'` |
| `cli/tests/test_routing.py -k "declared or undeclared or bound or forged"` | **12 failed**, 1 passed (the one pre-existing test the filter also selects) |
| `cli/tests/test_migrations.py -k "0_8_0 or repositor or repos"` | **4 failed**, 2 passed (pre-existing) |

## Results

| Row | Command | Outcome |
|-----|---------|---------|
| T1 | `pytest -q cli/tests/test_repositories.py` | **27 passed** |
| T2 | `pytest -q cli/tests/test_routing.py -k "declared or undeclared or bound or forged or host_disagreement or closing_keyword"` | **20 passed**, 173 deselected |
| T3 | `pytest -q cli/tests/test_poller.py` | **222 passed** |
| T4 | `pytest -q cli/tests/test_migrations.py cli/tests/test_cli_config.py` | **80 passed** |
| T5 | `pytest -q cli/tests/test_webhook_routing_integration.py -k "declared or undeclared or wire"` | **3 passed**, 36 deselected |
| T5 | `pytest -q cli/tests/test_poll_daemon_integration.py -k top_level` | **1 passed**, 8 deselected |
| T11 | the abuse cases, in T1/T2 above | **A1–A9 closed** — see [`security-review.md`](security-review.md) |
| T13 | `pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_manifest_schemas.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py` | **29 passed** |
| T13 | `python scripts/validate_config.py` | **7 VALID**, 0 invalid — including `.the-loop/cli-config.yaml` and the shipped template against the new schema |
| T15 | `make check` | **3471 passed, 1 skipped**; ruff, markdownlint (1065 files, 0 errors), `ruff format --check` (293 files), pyright (0 errors) and config validation all clean |
| T16 | [`security-review.md`](security-review.md) | A1–A9 closed; **tier 4 — a named human security sign-off is outstanding** until the owner signs at the PR |

Baseline for comparison: `make check` on `35a08cf` was 3418 passed / 1 skipped at
13.11.1 and 3443 at 13.12.0's merge base; this branch adds 28 tests net.

## Requirement trace

| Requirement | Where it is proved |
|---|---|
| R1.1, R1.4, R1.5 | `test_the_declared_set_is_the_top_level_key`, `test_the_set_is_deduplicated_by_key`, `test_a_declared_entry_keeps_the_operators_own_slug` |
| R1.2 | `test_a_bare_entry_takes_this_instances_host`, `test_a_bare_entry_takes_a_configured_enterprise_host`, `test_a_qualified_entry_keeps_its_host` |
| R1.3 | `test_a_malformed_entry_is_skipped` (9 cases), `test_an_over_segmented_entry_is_skipped`, `test_a_broken_section_narrows_rather_than_widens` |
| R1.6 | `test_the_builder_imports_without_channels` — a subprocess import of `the_loop.repos` loads no `the_loop.channels.*` module |
| R2.1 | `test_a_delivery_from_a_declared_repository_routes`, `test_a_delivery_from_an_undeclared_repository_is_dropped`, `Scenario: A delivery for a repository the operator never declared…` |
| R2.2 | `test_a_ref_outside_the_declared_set_is_filtered_out`, `test_a_delivery_whose_every_ref_is_undeclared_is_dropped` |
| R2.3 | `test_no_declared_repositories_bounds_nothing`, `test_repository_bounds_is_none_when_nothing_is_declared` |
| R2.4 | `test_the_repository_bound_is_checked_before_the_actor` (the recorded drop carries `repository` and no `actor`), `test_an_undeclared_delivery_publishes_nothing_to_the_bus` |
| R2.5 | `Scenario: Declaring the repository and reloading routes the next delivery` |
| R2.6 | `test_an_undeclared_delivery_is_not_marked_processed`, `Scenario: A refusal discloses nothing about what the operator declared` |
| R3.1, R3.2 | `test_provider_from_source_takes_its_repositories_from_the_caller`, `test_the_daemon_binds_sources_to_the_resolved_host` (4 cases), `Scenario: The poller builds its GitHub source from the top-level repositories` |
| R3.3 | the issue-315 isolation suite in `test_poller.py`, unchanged and green |
| R3.4 | `test_a_provider_with_no_repositories_names_the_top_level_key` |
| R3.5 | `test_a_source_still_declaring_repos_is_refused` |
| R4.1 | `test_may_target_every_declared_repository`, `test_a_failing_read_contributes_nothing` |
| R4.2, R4.3 | `test_channels_kickoff.py` (43 passed), `test_channels_integration.py` kickoff scenarios |
| R4.4 | `channels status` reads `declared_repositories`; `test_status_names_the_fallback_and_how_many_a_prefix_may_pick` |
| R5.1, R5.2, R5.6 | `test_the_repository_lists_move_up`, `test_the_kickoff_repo_joins_the_declared_set_and_stays_where_it_is`, `test_a_hand_written_top_level_list_is_kept_first` |
| R5.3 | `test_the_repositories_migration_is_idempotent` |
| R5.4, R5.5 | `test_an_un_migrated_repos_key_is_refused`, `test_the_current_config_version_is_0_8_0` |

## Existing assertions changed, and why

| Test | Change | Why |
|---|---|---|
| `test_channels_kickoff.py::test_the_declared_set_is_kickoff_repo_and_every_poll_source` | renamed `…_is_the_top_level_declaration`; the two source-shape assertions (`test_a_non_github_source_is_ignored`, `test_a_malformed_polling_section_widens_nothing`) moved to `test_repositories.py` in their new form | they pinned where the set came *from*, which is what this work item changes |
| `test_channels_kickoff.py::test_refusal_text_with_no_declared_repositories` | asserts the refusal names `repositories`, and no longer names `polling.sources` | the wording follows the key |
| `test_channels_commands.py::test_may_target_kickoff_repo_and_poll_sources` | renamed `…_every_declared_repository`, reads the top-level list | same |
| `test_poller.py` — five provider tests | `repos` moved from the source dict to the `repositories=` argument | the seam the design moves |
| Nine fixture configs (`test_client`, `test_core_daemons`, `test_envfile*`, `test_ghhost_integration`, `test_instance`, `test_state_root_integration`) | `version: '0.7.0'` → `'0.8.0'` | the version gate; these fixtures assert *no* staleness complaint |
| Four fixture configs (`test_poll_command`, `test_poll_daemon_integration`, `test_hosted_ingress_integration`, `test_channels_integration`) | `polling.sources[].repos` → top-level `repositories` | the retired key would now refuse to load |
| `test_core_lifecycle.py`, `test_api_health_integration.py` `_config` | declare `repositories` | an enabled poller with none is now reported `misconfigured` (see the execution log) |

Nothing was deleted to make a test pass, and no test was skipped, disabled or quarantined.

## Redaction

No tokens, no member ids, no hostnames beyond the fixtures (`octo/…`, `ghe.corp`,
`ghe.corp.example`, `stranger/repo`, `attacker/repo`), no paths outside the repository and
its pytest tmp dirs.
