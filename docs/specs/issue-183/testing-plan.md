---
type: testing-plan
phase: test-planning
workItem: issue-183
status: approved              # draft | in-review | approved
approvedBy: []                # pending — reviewed with design.md at one gate
overrides: {}
---

# Testing plan: multi-repo work items — the outer loop stays in the origin repo

> Derived from `requirements.md` and `design.md`, reviewed with the design at one gate, and
> locked before `tasks.md`. Executed at the `verification` node, which fills in
> § Verification results below.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `repo_state_key`, `inner_loop_state_dir`, `await_inner_loops` (declared repos, both layouts), `outer_loop_surface`, `linked_work_items`, `render_assignment`/`render_graph_context` surface + `--pr-repo` claim | `uv run --directory cli pytest -q` |
| T2 | Integration (scenario) | yes | a cross-repo pull request routes to its work item, walks an inner loop whose state lands under the origin repo's spec directory, and holds the outer `implementation` gate until it completes | `uv run --directory cli pytest -q cli/tests/test_graph_multirepo_integration.py` |
| T3 | Contract (OpenAPI) | yes | the authored contract gains an optional `prRepo` on the five graph bodies and the `graphShow` query, and the served schema still matches it route-for-route | `uv run --directory cli pytest -q tests/test_api_contract_parity.py` |
| T4 | End-to-end | n/a — an end-to-end run needs a live GitHub app and two real repositories; T2 exercises the same seams against the shipped router, runtime and hooks with no network. | | |
| T5 | UI / visual | n/a — no user-facing surface (CLI + markdown). | | |
| T6 | Snapshot | n/a — no rendered output is snapshotted in this repository. | | |
| T7 | Performance / load | n/a — the added work is one extra `glob` over a directory that holds one entry per pull request. | | |
| T8 | Security / abuse case | yes | the four abuse cases of `design.md` § Security design: path traversal from a payload, from `--pr-repo`, an unarmed work item reached by a cross-repo link, and a declared repo that never gets a pull request | `uv run --directory cli pytest -q -k "traversal or pr_repo or unarmed or declared"` |
| T9 | Accessibility | n/a — no UI. | | |
| T10 | Migration / upgrade | yes | an existing work item's `pr-loops/pr-<n>/` keeps resolving unchanged, and a config with no `workflow.outerLoop` resolves `pull-request` | `uv run --directory cli pytest -q -k "back_compat or default"` |
| T11 | Manual exploratory | n/a — every behaviour is reachable from a test; nothing here needs a human to look at it. | | |
| T12 | Parity (docs ↔ code ↔ schema) | yes | the new config key is in the schema, in `READS`, and in `docs/config/harness-config.md`; every CLI flag is documented | `uv run --directory cli pytest -q cli/tests/test_docs_parity.py cli/tests/test_harness_config.py cli/tests/test_graph_parity.py` |
| T13 | Lint / type / format | yes | ruff, ruff format, pyright, markdownlint, and the harness-config schema validator | `make lint typecheck` (or the individual commands) |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.3, R1.4, R1.6 | `pr-loops/pr-7` for the origin repo, `pr-loops/octo__infra/pr-7` for a contributing one; every malformed repo value raises |
| T1 | R2.1–R2.3, R2.6 | the surface resolves to `pull-request` when absent/unknown; the assignment names it |
| T1 | R1.5 | a qualified closing keyword yields a ref in the *other* repository; an unqualified one stays local |
| T1 | R4.1–R4.4 | `await-inner-loops`: pass, wait-on-unfinished, wait-on-undeclared-loop, wait-on-declared-repo-with-no-loop, wait-on-unknown-origin |
| T2 | R1.1–R1.5, R4.1 | `Scenario: a pull request in a contributing repository walks its own inner loop under the work item's spec directory` |
| T2 | R4.2 | `Scenario: the work item holds at implementation until every declared repository has finished` |
| T8 | abuse cases 1–4 | negative tests named in `design.md` § Security design |
| T10 | R1.4, R2.2 | a pre-existing `pr-loops/pr-<n>/` and a config with no `outerLoop` behave as before |

## Verification environment

- **Repositories:** this repository only. The multi-repo behaviour is exercised with
  fixture directories and synthesised payloads — no second checkout, no network.
- **Services / containers:** none.
- **Fixtures & data:** `tmp_path` trees written by the tests; webhook payloads built in-test
  from the shapes already used in `cli/tests/test_poller.py` and `test_graph_loops.py`.
- **Credentials:** none. No test in this work item authenticates to anything.
- **Bring-up:** `uv sync --directory cli` · **Tear-down:** none (pytest `tmp_path`).
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T10, T12 | full suite output (counts, duration) and the red→green transitions | `tests.md` |
| T13 | ruff / ruff format / pyright / markdownlint / schema-validator output | `lint.md` |
| T2 | the scenario walk-through against the shipped graph and router | `multirepo-scenario.md` |

## Verification activities

- [x] T1 — `uv run --directory cli pytest -q` (unit)
- [x] T2 — `uv run --directory cli pytest -q tests/test_graph_multirepo_integration.py`
- [x] T8 — the four abuse-case tests, red before the mechanism existed
- [x] T10 — back-compat: existing `pr-loops/pr-<n>/` and a config with no `outerLoop`
- [x] T3 — `uv run --directory cli pytest -q tests/test_api_contract_parity.py`
- [x] T12 — `pytest -q tests/test_docs_parity.py tests/test_harness_config.py tests/test_graph_parity.py`
- [x] T13 — `ruff check`, `ruff format --check`, `pyright`, `markdownlint`, `validate_config.py`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run --directory cli pytest -q` | pass — 1520 passed, 1 skipped | [`evidence/tests.md`](evidence/tests.md) |
| T2 | `uv run --directory cli pytest -q tests/test_graph_multirepo_integration.py` | pass — 6 passed | [`evidence/tests.md`](evidence/tests.md) |
| T8 | `uv run --directory cli pytest -q -k "traversal or pr_repo or unarmed or declared"` | pass — 70 passed; red recorded before the mechanisms existed | [`evidence/tests.md`](evidence/tests.md) |
| T10 | `uv run --directory cli pytest -q -k "back_compat or default"` | pass — 55 passed | [`evidence/tests.md`](evidence/tests.md) |
| T3 | `uv run --directory cli pytest -q tests/test_api_contract_parity.py` | pass — 1 passed | [`evidence/tests.md`](evidence/tests.md) |
| T12 | `uv run --directory cli pytest -q tests/test_docs_parity.py tests/test_harness_config.py tests/test_graph_parity.py` | pass — 31 passed | [`evidence/tests.md`](evidence/tests.md) |
| T13 | `uv run ruff check cli hooks`, `ruff format --check cli hooks`, `pyright cli`, `markdownlint-cli2 "**/*.md"`, `python scripts/validate_config.py` | pass | [`evidence/lint.md`](evidence/lint.md) |
| T2 (scenario) | scripted walk of the ticket's own scenario against the shipped router, runtime and hooks | pass | [`evidence/multirepo-scenario.md`](evidence/multirepo-scenario.md) |

**Not executed:** none — every planned activity ran. One pre-existing tmux integration test (`test_legacy_record_without_a_tmux_target_heals_via_respawn`, untouched by this work item) failed once under the full suite and passed both in isolation and on a full re-run — a flake in this container, recorded here rather than smoothed over.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
