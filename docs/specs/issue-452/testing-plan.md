---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#452"
status: in-review            # tier 3: locked with design.md at the PR
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: a work item's terminal record outlives its checkout

> Derived from [`bugfix.md`](bugfix.md) and [`design.md`](design.md). Planned at
> `test-planning`, results recorded at `verification` (below).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `archive.terminal_record` over a real runtime and state file: completed vs mid-flight, frozen selections, pull requests, evidence; `closure_outcome` and `cancelled` truth tables; `archived_report` shape | `cd cli && uv run pytest tests/test_archive.py` |
| T2 | Unit (core) | yes | `core.graphs.check`: archived report for a ref with a stamp and no state file; unchanged with a state file, with a bare id, with `--recompute` over an existing spec directory; `detail: unavailable` without a terminal record | `cd cli && uv run pytest tests/test_archive.py` |
| T3 | Unit (dispatcher) | yes | the closure stamps `outcome` + `terminal` read before the checkout is removed; a not-planned close is `cancelled`; a session-less tracked close; the cleanup verb backfills a stamp that lacks a record | `cd cli && uv run pytest tests/test_archive_dispatch.py` |
| T4 | Unit (poller) | yes | `item_state` reads `state_reason`; the synthesized closure carries it on the `issue` entity | `cd cli && uv run pytest tests/test_archive_dispatch.py` |
| T5 | Integration (scenario, Gherkin-docstringed) | yes | a real dispatcher and a real git worktree, `keepCheckoutOnClose: false`: the item completes, the ticket closes, the worktree and session record go; then `the-loop check <ref> --format json --fail-on block` from an unrelated directory reports `archived.outcome: completed` and exits 0; the same through a freshly built store (daemon restart); the table says `ARCHIVED — completed` | `cd cli && uv run pytest tests/test_archive_integration.py` |
| T6 | Contract (OpenAPI) | yes | the authored contract still matches the served schema (descriptions changed, surface did not) | `cd cli && uv run pytest tests/test_api_contract_parity.py` |
| T7 | Security / abuse case | yes | a forged skip of a non-skippable node, a node id the graph lacks, a PR row with a forged URL and evidence names carrying an escape sequence or `..` are all filtered; a foreign or missing checkout yields `unknown`, never `completed` | with T1, T3 |
| T8 | End-to-end (live) | no — the reproduction is a live daemon run against `the-loop-testing`; T5 drives the same close path, worktree removal included, in-process | | |
| T9 | UI / visual, snapshot, accessibility, performance | n/a — CLI text asserted directly in T5; one extra file read per closure | | |
| T10 | Migration / upgrade | yes | a stamp written before this change (six keys, no `terminal`) is reported as archived with `detail: unavailable` | with T2 |
| T11 | Regression (full suite) | yes | every closure, cleanup, graph, check, API and poller suite stays green | `cd cli && uv run pytest -q` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.2, R1.3 | a state whose `complete` record has an outcome → `completed: true`; a state at `human-approval` → `completed: false`; skips/opt-ins/choices/PRs copied |
| T2 | R2.1–R2.4, R2.6 | `check(cwd, ref)` with a stamp → `archived`, `nodes: []`, `currentNode` = recorded node; with a state file present → unchanged; `check(cwd, "issue-3")` → unchanged |
| T3 | R1.1, R1.2, R1.4, R1.5, R1.7 | stamp written while the checkout existed; `state_reason: not_planned` → `cancelled`; merged PR without completion claim → `closed-externally`; cleanup on a stamp with no record adds one |
| T4 | R1.6 | REST `state_reason: not_planned` → `Closure.reason` → `payload.issue.state_reason` |
| T5 | R2.5, R2.6, R2.7 | `Scenario: a completed work item is checked after normal cleanup` and `Scenario: the daemon restarts between cleanup and check` |
| T7 | security | as the matrix row |
| T10 | R2.2 | `Scenario: a stamp from before the change` |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none; `THE_LOOP_SERVICE_LOCAL=1` (set by the test
  configuration) keeps the CLI in-process.
- **Fixtures & data:** a throwaway origin repository, a worktree workspace, a state file,
  a CLI config and a portable directory written per test under `tmp_path`.
- **Credentials:** none.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record under Verification results, leave the rows unticked.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1–T7, T10 | test names and run output, red → green noted | `verification.md` |
| T11 | full-suite, lint, format, typecheck output | `verification.md` |

## Verification activities

- [x] T1 + T2 + T10 — `cd cli && uv run python -m pytest -q tests/test_archive.py`
- [x] T3 + T4 + T7 — `cd cli && uv run python -m pytest -q tests/test_archive_dispatch.py`
- [x] T5 — `cd cli && uv run python -m pytest -q tests/test_archive_integration.py`
- [x] T6 — `cd cli && uv run python -m pytest -q tests/test_api_contract_parity.py`
- [x] T11 — `cd cli && uv run python -m pytest -q` · `uv run ruff check cli hooks` · `uv run ruff format --check cli hooks` · `uv run pyright cli`

## Verification results

Recorded in [`evidence/verification.md`](evidence/verification.md).

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 + T2 + T10 | `cd cli && uv run python -m pytest -q tests/test_archive.py` | pass — 30 passed (import error before the fix) | `evidence/verification.md` |
| T3 + T4 + T7 | `cd cli && uv run python -m pytest -q tests/test_archive_dispatch.py` · `tests/test_poller.py tests/test_ghapi.py tests/test_poller_integration.py` | pass — 12 and 333 passed (red before the fix) | `evidence/verification.md` |
| T5 | `cd cli && uv run python -m pytest -q tests/test_archive_integration.py` | pass — 4 passed (all 4 red before the fix) | `evidence/verification.md` |
| T6 | `cd cli && uv run python -m pytest -q tests/test_api_contract_parity.py` | pass — 4 passed | `evidence/verification.md` |
| T11 | full suite · ruff · ruff format · pyright · markdownlint | pass — 5345 passed, 1 skipped; all clean | `evidence/verification.md` |
| T8 | live daemon run against `the-loop-testing` | not run — needs a daemon, a token and a second repository; T5 drives the same path in-process | — |

## Review comments

*None yet.*
