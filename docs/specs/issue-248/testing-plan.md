---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#248"
status: in-review             # draft | in-review | approved
approvedBy: []
collaborators: [engineer]
overrides: {}
---

# Testing plan: a repository may bring its own graph hooks

> Derived from the approved `requirements.md` and `design.md`, **before** `tasks.md` — each
> task's `_Test:_` names a row of the matrix below. Authored at `test-planning` and
> completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `extensions.read_declaration` / `load_modules` / `apply`, the registry collector, `Graph.hook_for`, the outcome drop in `run_chain` | `make test` (`cli/tests/test_graph_extensions.py`) |
| T2 | Integration (scenario) | yes | a real repository tree declaring a hook module: loaded, appended, run, and reported by `the-loop check` — Gherkin-documented | `make test` (`cli/tests/test_graph_extensions_integration.py`) |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — this work item adds no API operation; the control plane's contract is untouched. | | |
| T4 | End-to-end | n/a — the shipped PDLC e2e runner (`test_pdlc_e2e`) walks the loop with no repository hooks declared, which is exactly the R1.6 "unchanged when absent" case T1 asserts directly. | | |
| T5 | UI / visual | n/a — no product UI (design § UI/UX). | | |
| T6 | Snapshot | n/a — no rendered artifact is snapshotted; the CLI action's output is asserted field-wise. | | |
| T7 | Performance / load | n/a — one import per module per process, on a path that already reads two YAML files. | | |
| T8 | Security / abuse case | yes | one negative test per abuse case in `design.md` § Security design | `make test` |
| T9 | Accessibility | n/a — no UI. | | |
| T10 | Migration / upgrade | yes | a repository with no `graph.hooks` block, and one written against the pre-rename `config.yaml`, both keep working | `make test` |
| T11 | Manual exploratory | yes | `the-loop graph hooks` and `the-loop check` run by hand against this repository with a sample hook module, to confirm the operator-facing text reads the way the docs claim | terminal |
| T12 | Docs/schema parity | yes | `graph.hooks` resolves in the harness schema, is documented as CLI-read, and the new CLI-config key has an option page | `make test` (`test_harness_config.py`, `test_docs_parity.py`) |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1–R1.4 | a declaration naming a `path` module and an attachment produces a graph whose node chain ends in the `x-` hook |
| T1 | R1.6 | a repository with no block compiles to a graph identical to the shipped one, and imports nothing |
| T1 | R2.1 | `apply` appends; the shipped entries keep their order and their position |
| T1 | R2.3, R2.4 | `run_chain` drops an `x-` hook's `data["outcome"]` and logs that it did |
| T1 | R2.5 | an attachment naming an undeclared node, or a boundary other than entry/exit, fails to load |
| T1 | R3.1–R3.3 | the collector refuses a non-`x-` registration; `@hook` refuses an `x-` name outside it |
| T1 | R3.4 | two repositories declaring the same `x-` name each resolve their own function |
| T1 | R4.1, R4.2 | missing module, module that raises, module that registers nothing, attachment naming an unregistered hook |
| T1 | R5.3 | absolute path, `..` escape, symlink out of the tree, non-`.py` suffix |
| T2 | R1.5 | `Scenario: a repository's own hook gates a node for the CLI and the daemon alike` |
| T2 | R1.1, R1.3 | `Scenario: a repository declares a hook module and the loop runs it at the boundary it named` |
| T2 | R4.1, R4.4 | `Scenario: a hook module that cannot be imported stops the loop instead of quietly disappearing` |
| T2 | R5.1 | `Scenario: the operator inspects a repository's hook declarations without importing them` |
| T2 | R5.2 | `Scenario: the operator refuses repository hooks and nothing from the repository is imported` |
| T8 | abuse 1 | `test_a_repository_hook_cannot_rescue_a_blocked_chain` |
| T8 | abuse 2 | `test_a_repository_hook_cannot_declare_an_outcome` |
| T8 | abuse 3 | `test_a_module_outside_the_repository_is_refused` |
| T8 | abuse 4 | `test_a_module_registering_a_shipped_name_fails_to_load` |
| T8 | abuse 5 | `test_two_repositories_keep_their_own_implementations` |
| T8 | abuse 6 | `test_a_raising_repository_hook_blocks` |
| T8 | abuse 7 | `test_the_operator_kill_switch_imports_nothing` |
| T10 | R1.6 | the shipped graphs still compile with `repo=` pointing at a repository that has no harness config at all |
| T12 | R1.1 | `graph.hooks` is in `READS`, resolves in the schema, and appears in the harness-config doc's read table |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none — every test is filesystem-local (`tmp_path` repositories).
- **Fixtures & data:** hook modules written into `tmp_path` by the tests themselves; no
  checked-in fixture executes.
- **Credentials:** none. No test reaches the network.
- **Bring-up:** `uv sync --project cli` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T10, T12 | test run output (counts, duration) | `unit-and-integration.md` |
| T1, T2 | lint + typecheck output | `lint-and-typecheck.md` |
| T8 | security review record | `security-review.md` |
| T11 | terminal transcript of `graph hooks` and `check` against a sample module | `manual.md` |

## Verification activities

- [x] T1/T2/T8/T10/T12 — `make test`
- [x] T1/T2 — `make lint && make typecheck`
- [x] T8 — security review of the diff, recorded (human sign-off still pending)
- [x] T11 — `the-loop graph hooks` and a real runtime evaluation against a sample module

## Verification results

Executed 2026-08-18 on `claude/github-issue-248-o4u7z7`.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1/T2/T8/T10/T12 | `make test` | 2412 passed, 1 skipped (2405 before this change; 48 of the new ones are this work item's) | [unit-and-integration.md](evidence/unit-and-integration.md) |
| T1/T2 | `make lint` · `make typecheck` | ruff clean, markdownlint 0 errors over 807 files, pyright 0 errors | [lint-and-typecheck.md](evidence/lint-and-typecheck.md) |
| T12 | `uv run --with jsonschema python scripts/validate_config.py` | all seven configs valid against the changed schemas | [lint-and-typecheck.md](evidence/lint-and-typecheck.md) |
| T8 | security review of this work item's diff, boundary by boundary | two findings, both accepted and documented; no change required | [security-review.md](evidence/security-review.md) |
| T11 | a hand-built repository declaring one module and one attachment, driven with `the-loop graph hooks`, `the-loop check` and a real `build_runtime` evaluation | the hook blocked the node with its own message, passed once the file was fixed, and never ran behind a shipped gate that blocked first | [manual.md](evidence/manual.md) |

**Not executed:** none. The one activity replanned is T4 (end-to-end): the shipped PDLC e2e
runner walks a repository that declares no hooks, which is the R1.6 case
`test_a_repository_that_declares_nothing_is_untouched` asserts directly — the matrix marked
it `n/a` for that reason and the run confirmed it (the e2e suite is green, unchanged).

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
