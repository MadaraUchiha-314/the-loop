---
type: testing-plan
phase: test-planning
workItem: "issue-348"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: one declared set, four readers, and a break that refuses to be ignored

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `the_loop/repos.py`: the set built from the top-level key alone, declaration order, dedup by normalized key with the first spelling kept, the operator's own slug preserved, a malformed entry skipped, a non-list section contributing nothing, `kickoff.repo` **not** contributing, `repository_bounds` returning `None` for absent/empty and a set otherwise, and the module importable without `channels` | `uv run --project cli python -m pytest -q cli/tests/test_repositories.py` |
| T2 | Unit | yes | `webhook/router.py`: a delivery from a declared repository routes; one from an undeclared repository drops with `undeclared-repository`; the drop precedes the actor check and publishes nothing to the bus; refs outside the set are filtered while the rest survive; all-refs-outside drops; `repositories=None` routes everything exactly as 13.12.0; host disagreement between `full_name` and `html_url` drops; a dropped delivery is not marked processed | `uv run --project cli python -m pytest -q cli/tests/test_routing.py -k "declared or undeclared or bound"` |
| T3 | Unit | yes | `poller/`: a provider takes its repositories from the caller; a source still carrying `repos` raises `ProviderError` naming the replacement; an empty set raises the "no repositories" error naming the top-level key; `provider`/`label`/`monitor`/`ghBinary` still come from the source; the issue-315 per-repository failure isolation unchanged | `uv run --project cli python -m pytest -q cli/tests/test_poller.py` |
| T4 | Unit | yes | `migrations.py`: `polling.sources[].repos` + `kickoff.repo` → top-level `repositories`, in order, deduplicated; a hand-written top-level list is kept and ordered first; a non-`github` source is left alone; idempotent on a second run; `needs_migration` true; `assert_current` raises `ConfigTooOld` naming key, replacement and command; `CURRENT_CONFIG_VERSION == "0.8.0"` | `uv run --project cli python -m pytest -q cli/tests/test_cli_config.py cli/tests/test_migrations.py` |
| T5 | Integration (scenario) | yes | through the receiver and the poller as they are actually composed: a signed delivery for an undeclared repository is acknowledged, dispatches nothing and leaves the event log saying why; the same delivery after the repository is declared dispatches; a hot-reload that adds a repository takes effect on the next delivery; the poller builds its provider from the top-level key and polls those repositories | `uv run --project cli python -m pytest -q cli/tests/test_webhook_routing_integration.py cli/tests/test_poll_daemon_integration.py -k "declared or undeclared or repositories"` |
| T6 | Contract (OpenAPI / GraphQL SDL) | n/a — no API route, request or response shape changes; the control-plane surface reads the same config it always did | | |
| T7 | End-to-end | n/a — an end-to-end run needs a real GitHub delivery and a real `gh`; T5 exercises the same composition with the injected fakes the suite already uses | | |
| T8 | UI / visual | n/a — no UI of the-loop's own is touched (the dashboard reads the control-plane API, unchanged) | | |
| T9 | Snapshot | n/a — assertions are on dataclasses, drop reasons, call arguments and rendered YAML | | |
| T10 | Performance / load | n/a — one set build per delivery over a list an operator wrote by hand, and one set lookup per work-item ref | | |
| T11 | Security / abuse case | yes | one negative test per abuse case A1–A9 (`requirements.md` § Security considerations): a forged authorized actor on an undeclared repository; a `full_name`/`html_url` host disagreement; a cross-repository closing keyword from an undeclared repository; a linked ref into an undeclared repository; an un-migrated config refusing rather than widening; metacharacter and over-segmented entries; an Enterprise host not admitting its github.com namesake; a broken section narrowing rather than widening; no repository name in anything sent back on the wire | `uv run --project cli python -m pytest -q cli/tests/test_routing.py cli/tests/test_repositories.py -k "abuse or forged or undeclared or host or malformed"` |
| T12 | Accessibility | n/a — no UI of the-loop's own | | |
| T13 | Migration / upgrade | yes | both schema copies byte-identical; the shipped template and this repository's own config validate against the new schema; docs parity P3/P4/P5 for the new key and the removed one; the event catalog knows `undeclared-repository`; the manifest/schema suites green | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_manifest_schemas.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py && uv run --project cli python scripts/validate_config.py` |
| T14 | Manual exploratory | n/a — no GitHub app delivery is reachable from this session; the reviewer's walk-through is the PR briefing's "what to check" | | |
| T15 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T16 | Security review (gate) | yes | the-loop checklist against A1–A9, recorded as evidence. Tier 4 **requires a named human security sign-off** (`security.review.humanSignOffMinTier: 4`) — recorded as outstanding until the owner signs at the PR | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.4, R1.5 | `test_the_declared_set_is_the_top_level_key`, `test_the_set_is_deduplicated_by_key`, `test_a_declared_entry_keeps_the_operators_own_slug` |
| T1 | R1.2 | `test_a_bare_entry_takes_this_instances_host`, `test_a_bare_entry_takes_a_configured_enterprise_host`, `test_a_qualified_entry_keeps_its_host` |
| T1 | R1.3 | `test_a_malformed_entry_is_skipped`, `test_an_over_segmented_entry_is_skipped`, `test_a_broken_section_narrows_rather_than_widens` |
| T1 | R1.6 | `test_the_builder_imports_without_channels` |
| T1 | R2.3 | `test_repository_bounds_is_none_when_nothing_is_declared`, `test_repository_bounds_is_a_set_when_something_is` |
| T1 | R4.2 (D2) | `test_kickoff_repo_no_longer_declares_a_repository` |
| T2 | R2.1 | `test_a_delivery_from_a_declared_repository_routes`, `test_a_delivery_from_an_undeclared_repository_is_dropped` |
| T2 | R2.2 | `test_a_ref_outside_the_declared_set_is_filtered_out`, `test_a_delivery_whose_every_ref_is_undeclared_is_dropped` |
| T2 | R2.3 | `test_no_declared_repositories_bounds_nothing` |
| T2 | R2.4 | `test_the_repository_bound_is_checked_before_the_actor`, `test_an_undeclared_delivery_publishes_nothing_to_the_bus` |
| T2 | R2.6 | `test_an_undeclared_delivery_is_not_marked_processed` |
| T3 | R3.1, R3.2 | `test_provider_from_source_takes_its_repositories_from_the_caller` (label and monitor still come from the source), `test_the_daemon_binds_sources_to_the_resolved_host` |
| T3 | R3.4 | `test_a_provider_with_no_repositories_names_the_top_level_key` |
| T3 | R3.5 | `test_a_source_still_declaring_repos_is_refused` |
| T3 | R3.3 | the existing issue-315 isolation tests, unchanged |
| T4 | R5.1, R5.2, R5.6 | `test_the_repository_lists_move_up`, `test_the_kickoff_repo_joins_the_declared_set_and_stays_where_it_is`, `test_a_hand_written_top_level_list_is_kept_first` |
| T4 | R5.3 | `test_the_repositories_migration_is_idempotent` |
| T4 | R5.4, R5.5 | `test_an_un_migrated_repos_key_is_refused`, `test_the_current_config_version_is_0_8_0` |
| T5 | R2.1, R2.5 | `Scenario: A delivery for a repository the operator never declared is acknowledged and dispatched nowhere`, `Scenario: Declaring the repository and reloading routes the next delivery` |
| T5 | R3.1 | `Scenario: The poller builds its GitHub source from the top-level repositories` |
| T11 | A1 | `test_a_forged_authorized_actor_on_an_undeclared_repository_is_dropped` |
| T11 | A2 | `test_a_host_disagreement_between_full_name_and_html_url_is_dropped` |
| T11 | A3 | `test_a_closing_keyword_from_an_undeclared_repository_reaches_nothing` |
| T11 | A4 | `test_a_linked_ref_into_an_undeclared_repository_is_filtered` |
| T11 | A5 | `test_an_un_migrated_repos_key_is_refused` |
| T11 | A6 | `test_a_malformed_entry_is_skipped` (nine cases), `test_an_over_segmented_entry_is_skipped` |
| T11 | A7 | `test_an_enterprise_host_does_not_admit_its_github_com_namesake` |
| T11 | A8 | `test_a_broken_section_narrows_rather_than_widens` (three cases) |
| T11 | A9 | `Scenario: A refusal discloses nothing about what the operator declared` |
| T13 | R1.1, R5.5 | `test_config_schema_parity.py`, `test_docs_parity.py`, `test_manifest_schemas.py`, `scripts/validate_config.py` |

## Verification environment

The repository checkout, `uv run --project cli`, no network. GitHub is never reached: the
receiver tests POST into the stdlib handler with fixture payloads and a fixture secret,
and the poller tests inject the existing fake `GhClient`. No credential is read; the
webhook secret is a `monkeypatch.setenv` fixture value and never appears in evidence.

## Evidence to capture

- `evidence/verification.md` — the commands of T1–T5, T11, T13, T15 with their pass/fail
  counts, and the red-first note for the new suites.
- `evidence/security-review.md` — A1–A9, each with the test that closes it, plus the
  explicit statement that tier 4 leaves a **named human security sign-off outstanding**
  until the owner signs at the PR.
- Redaction: no tokens, no hostnames beyond the fixtures (`octo/…`, `ghe.corp.example`),
  no paths outside the repository.

## Activities checklist

- [x] Red first: the new suites fail against `35a08cf`.
- [x] T1 unit suite green.
- [x] T2 receiver-bound unit tests green.
- [x] T3 poller unit tests green.
- [x] T4 migration unit tests green, both directions.
- [x] T5 scenarios green, each with a Gherkin docstring (`testing.gherkinDocstrings: required`).
- [x] T11 abuse cases green, one per A1–A9.
- [x] T13 schema/docs/config-validation suites green.
- [x] T15 `make check` green.
- [x] T16 security review recorded, human sign-off requested at the PR.

## Verification results

Executed 2026-09-11 on `claude/github-issue-348-vx9u2l`. Full output, the red-first note
and the requirement trace: [`evidence/verification.md`](evidence/verification.md).

| Row | Command | Outcome |
|-----|---------|---------|
| T1 | `pytest -q cli/tests/test_repositories.py` | **27 passed** |
| T2 | `pytest -q cli/tests/test_routing.py -k "declared or undeclared or bound or forged or host_disagreement or closing_keyword"` | **20 passed**, 173 deselected |
| T3 | `pytest -q cli/tests/test_poller.py` | **222 passed** |
| T4 | `pytest -q cli/tests/test_migrations.py cli/tests/test_cli_config.py` | **80 passed** |
| T5 | the receiver and poller-daemon scenarios | **3 passed** + **1 passed** |
| T11 | A1–A9, in the T1/T2 suites | **9 closed** — [`evidence/security-review.md`](evidence/security-review.md) |
| T13 | the four parity suites + `scripts/validate_config.py` | **29 passed**, **7 VALID** |
| T15 | `make check` | **3471 passed, 1 skipped**; ruff, markdownlint, format, pyright and config validation clean |
| T16 | [`evidence/security-review.md`](evidence/security-review.md) | A1–A9 closed; **tier 4 — a named human security sign-off is outstanding at the PR** |

Red first: `test_repositories.py` did not collect against `35a08cf`
(`ImportError: cannot import name 'repos' from 'the_loop'`); the new router cases failed
12/13 and the new migration cases 4/6 there.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
