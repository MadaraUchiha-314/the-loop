---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#396"
---

# Evidence: automated tests (issue-396)

Run on 2026-09-20, on the branch of the delivering PR, from the repository root unless
noted. Nothing in the output names a token, a host or a person.

## T1 + T7 — core: the translation, the fields, the pinned key sets

```
$ cd cli && uv run python -m pytest -q tests/test_core_graphs.py
20 passed in 0.62s
```

New or changed tests:

- `test_work_item_id_translates_a_ref_the_way_the_daemon_does` (7 cases — T1/T7,
  R1.1, R1.4: plain and host-qualified refs, a padded ref, a bare id, another
  provider's ref, a non-ref, and `../../etc#1`, which is passed through untranslated)
- `test_check_on_a_ref_reads_the_same_directory_as_on_the_id` (T1 — R1.1, R2.2)
- `test_check_names_the_state_file_it_read_or_looked_for` (T1 — R2.2)
- `test_a_resolving_repo_keeps_exactly_the_keys_it_always_had` (re-pinned to the two
  new keys; `test_the_unknown_position_answer_is_not_a_filesystem_oracle` unchanged —
  the no-path answer still has its six keys)

**Red first.** Before the production change: `AttributeError: module
'the_loop.core.graphs' has no attribute 'work_item_id'` (seven parametrised cases and
one scenario), `KeyError: 'statePath'` (one), and the re-pinned key set (one) — ten
failures.

## T2 + T7 — the CLI scenarios, in-process over a real checkout and registry

```
$ cd cli && uv run python -m pytest -q tests/test_graph_status_resolution.py
8 passed in 0.44s
```

All Gherkin-docstringed where they are scenarios:

- `test_a_ref_from_the_daemons_config_directory_reports_the_runtimes_node` (R1.1, R1.2,
  R2.1 — the B7/O6 reproduction: `at brainstorming`, `repo: … (from the session
  registry)`, `state: …/work-item-state.json`)
- `test_a_bare_id_from_a_foreign_directory_says_what_it_could_not_find` (R2.1)
- `test_an_explicit_repo_wins_over_the_registry` (R1.3)
- `test_inside_the_checkout_the_registry_is_not_consulted` (R1.3)
- `test_a_cleaned_up_checkout_falls_through_to_the_working_directory` (T7, fail-closed)
- `test_check_resolves_the_same_way_and_carries_the_fields` (R1.2, R2.1, R2.3)
- `test_check_all_prints_no_state_line` (R2.3)
- `test_a_mutating_verb_keeps_the_working_directory` (R1.4)

**Red first.** Before the fix all eight failed: the first printed `issue-1: at
phase-selection` with no `repo:` or `state:` line — the reported symptom, reproduced.

## T3 — the authored OpenAPI contract still matches the served schema

```
$ cd cli && uv run python -m pytest -q tests/test_api_contract_parity.py
2 passed
```

## T11 — full suite, lint, format, typecheck

Run from `cli/`, which is how the pre-commit hook and CI run it:

```
$ cd cli && uv run python -m pytest -q
4308 passed, 1 skipped in 169.10s (0:02:49)

$ uv run ruff check cli hooks
All checks passed!
$ uv run ruff format --check cli hooks
339 files already formatted
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
$ npx --yes markdownlint-cli2@0.18.1 <changed markdown files>
Summary: 0 error(s)
```
