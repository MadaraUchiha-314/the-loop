---
type: testing-plan
phase: test-planning
workItem: issue-193
status: approved
approvedBy: []
overrides: {}
---

# Testing plan: a default harness config for repositories that never adopted the-loop

> Derived from the approved `requirements.md` and `design.md`, **before** `tasks.md` —
> each task's `_Test:_` names a row of the matrix below. Authored at the `test-planning`
> node and **completed at the `verification` node**: the same file is written once as a
> plan and once as a record, so intent and outcome sit in one diff.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. Credentials appear **by reference only** — this change needs none.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `defaults()` and `scaffold()`: the written bytes, the provenance header, owner/repo substitution, idempotence, and each degradation path | `pytest cli/tests/test_harness_config.py` |
| T2 | Integration (scenario) | yes | the two real call sites: `GraphLink` adopting a git checkout with no `.the-loop/`, the contribution loop and the non-driving actions refusing to, and `core.graphs` mutating-vs-reading | `pytest cli/tests/test_harness_config_scaffold_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — the control-plane API gains no route and no field; `core.graphs._runtime` is internal | | |
| T4 | End-to-end | n/a — T2 drives the real `GraphLink` and the real `core.graphs` entry points against real git checkouts, which is as far as the daemon path goes without a live GitHub | | |
| T5 | UI / visual | n/a — no user-facing surface (design § UI/UX) | | |
| T6 | Snapshot | n/a — the one "golden file" is the packaged default, and T7 pins it by byte parity with the template rather than by a snapshot of its own output | | |
| T7 | Parity / drift (repo-level) | yes | the packaged default vs the `/the-loop:init` template (bytes), vs the schema, vs the graph's phase sequence, vs the module's per-key default constants | `pytest cli/tests/test_graph_parity.py cli/tests/test_harness_config.py` |
| T8 | Security / abuse case | yes | a negative test per trust boundary in `design.md` § Security design: forged owner/repo, foreign checkout, existing config, guest repository, escaping `.the-loop` symlink | `pytest … -k "forged or foreign or overwrite or contribution or escapes"` |
| T9 | Accessibility | n/a — no user interface | | |
| T10 | Migration / upgrade | yes | a repository that already carries a config — current name or the pre-rename `config.yaml` — is left untouched, so upgrading the-loop never rewrites an operator's policy | `pytest cli/tests/test_harness_config.py -k present` |
| T11 | Manual exploratory | n/a — every path is reachable from the test suite; a manual run would exercise the same two functions with less coverage | | |
| T12 | Regression (whole suite) | yes | every existing test still passes: adoption now writes a file into checkouts many of them build without one | `make test` |
| T13 | Lint / type-check | yes | repository gates: `ruff`, `pyright`, `markdownlint` over the new module code and the new markdown | `make lint format-check typecheck validate` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.4 | `defaults()` returns the packaged mapping; an unreadable package file yields `{}` |
| T1 | R2.1, R2.2 | `scaffold()` writes the file and names owner/repo under `ticketing.github` |
| T1 | R2.4, R2.5 | a second call returns `"present"`; an unwritable tree returns `""` |
| T2 | R2.1, R2.3 | `Scenario: the ingress adopts a repository that never ran the-loop's setup` |
| T2 | R2.1 | `Scenario: an adopted repository's graph is still skipped while the work item has no spec directory` |
| T2 | R4.1, R4.2 | `Scenario: a contribution never adopts its host repository` |
| T2 | R3.1, R3.2 | `Scenario: a mutating graph verb adopts, a read-only one does not` |
| T2 | R2.1 | `Scenario: resolving a prompt's graph context adopts nothing` (self-review) |
| T2 | R2.1 | `Scenario: releasing a work item's resources adopts nothing` (self-review) |
| T7 | R1.2, R1.3 | the packaged default is byte-identical to the template, valid against the schema, and declares the graph's phase sequence |
| T7 | R1.1 | `DEFAULT_SPEC_DIR` and the runtime's `phaseLabelPrefix` fallback equal what the packaged default declares |
| T8 | abuse 1 | `Scenario: a forged owner is dropped rather than written into the YAML` |
| T8 | abuse 2 | `Scenario: a checkout that is not the work item's repository is never adopted` |
| T8 | abuse 3 | `Scenario: an existing harness config is never overwritten` |
| T8 | abuse 4 | covered by the contribution scenario above |
| T8 | abuse 5 | `Scenario: a committed .the-loop symlink does not redirect the write` (security review) |
| T10 | R2.4 | a pre-rename `config.yaml` counts as adopted; nothing is written beside it |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. The tests that need a repository run `git init` in a
  `tmp_path`; GitHub is never contacted (the existing `fake_github` double serves the
  hooks).
- **Fixtures & data:** the shipped `cli/tests/conftest.py` doubles; no recorded traffic.
- **Credentials:** none — this change reads no environment and no secret.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate — do not pass the gate on an environment that never
  came up.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T7, T8, T10 | targeted run: command + raw output | `unit-and-integration.md` |
| T12 | whole-suite run: counts, duration, raw tail | `regression.md` |
| T13 | lint + type-check output | `lint-and-typecheck.md` |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_harness_config.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_harness_config_scaffold_integration.py`
- [x] T7 — `uv run --project cli python -m pytest -q cli/tests/test_graph_parity.py` + `uv run python scripts/validate_config.py`
- [x] T8 — `uv run --project cli python -m pytest cli/tests/test_harness_config.py cli/tests/test_harness_config_scaffold_integration.py -k "forged or foreign or overwrite or contribution or escapes"`
- [x] T10 — `uv run --project cli python -m pytest cli/tests/test_harness_config.py -k "present or pre_rename or overwrite"`
- [x] T12 — `make test`
- [x] T13 — `make lint format-check typecheck validate`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `pytest cli/tests/test_harness_config.py` | pass — 37 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T2 | `pytest cli/tests/test_harness_config_scaffold_integration.py -v` | pass — 9 passed, one per scenario | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T7 | `pytest cli/tests/test_graph_parity.py` · `scripts/validate_config.py` | pass — 9 passed; the packaged default reported `VALID` against the harness schema in its own right | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T8 | `pytest … -k "forged or foreign or overwrite or contribution or escapes"` | pass — 10 selected, 10 passed (one per abuse case; the forged-input row is parametrized six ways) | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T10 | `pytest cli/tests/test_harness_config.py -k "present or pre_rename or overwrite"` | pass — 3 selected, 3 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T12 | `make test` | pass — 1715 passed, 1 skipped; 29 of those are this work item's (19 unit, 9 integration, 1 new parity parametrization) | [`evidence/regression.md`](evidence/regression.md) |
| T13 | `make lint` · `format-check` · `typecheck` · `validate` | pass — ruff clean, 523 markdown files 0 errors, pyright 0 errors, 7 configs VALID | [`evidence/lint-and-typecheck.md`](evidence/lint-and-typecheck.md) |

**Not executed:** none — every activity in the matrix ran, and none was replanned.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
