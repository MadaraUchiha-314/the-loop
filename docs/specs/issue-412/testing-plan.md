---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#412"
status: approved
approvedBy: ["the-loop"]     # locked with bugfix.md; tier 2
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: four `test_instance.py` tests read the machine they run on

> Derived from [`bugfix.md`](bugfix.md). Planned at `test-planning`, results recorded at
> `verification` — see [`evidence/verification.md`](evidence/verification.md).

## What "proved" means here

The change is *to the tests*, so the suite cannot be its own evidence in the usual way: a
green run proves nothing unless it is green in **every row of the ticket's table**. The
plan is therefore a matrix of environments, not of test types — the same commands, run
under each combination of working directory and machine state, plus a full-suite run to
show the fixture costs nothing elsewhere.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (the four tests, 4 environments) | yes | the four argv tests pass from the repo root and from `cli/`, with and without `~/.the-loop/cli-config.yaml` — every row of the ticket's table, including the three that were red (AC1) | `pytest tests/test_instance.py` from each cwd × home state |
| T2 | Regression (full suite, worst case) | yes | the fixture changes no other test's answer; run with the home config **present**, the state that makes a contributor's machine red (AC2) | `cd cli && uv run python -m pytest -q` |
| T3 | Regression (full suite, repo root) | yes | the suite is hermetic from the other working directory too, so AC2 does not depend on the cwd it happens to be run from | `uv run --project cli python -m pytest -q cli` |
| T4 | Parity (the claim itself) | yes | `make test` and the pre-commit `pytest` hook are the same command string, cwd included; `make check` is green on the tree CI calls green (AC2, AC3) | `make check`, plus a diff of the two entries |
| T5 | Negative control | yes | the four tests still **fail** on `main` in the rows the ticket names — so T1 is evidence of a fix, not of a suite that never had the bug | `git stash` + T1 |
| T6 | Contract (OpenAPI) | n/a — no route, parameter or response changed | | |
| T7 | End-to-end (live) | n/a — no runtime code changed; nothing new spawns, polls or talks to GitHub or Slack | | |
| T8 | UI / visual | n/a — no rendered artifact changes | | |
| T9 | Snapshot | n/a — no golden files | | |
| T10 | Performance / load | n/a — one `setenv` per test in one module | | |
| T11 | Security / abuse case | yes | the pinned value is a test-owned `tmp_path`, never an operator path; no credential, token or home-directory content is read or written, and the export path itself is unchanged | review + T2 |
| T12 | Accessibility | n/a | | |
| T13 | Migration / upgrade | n/a — no key, state or schema change; the fixture is test-only and the Makefile target is a developer convenience | | |
| T14 | Manual exploratory | no — the ticket's table is the exploration, and T1 automates all four of its rows | | |

## Scenarios & requirement trace

| Row | Acceptance criterion | Scenario / case |
|-----|----------------------|-----------------|
| T1 | AC1 | repo root + no home config (was red); `cli/` + no home config (was green); `cli/` + home config (was red); repo root + home config (was red) |
| T2, T3 | AC2 | the whole suite, both working directories, home config present |
| T4 | AC2, AC3 | `make test` string == pre-commit `pytest` entry; `make check` green |
| T5 | AC1 | the same four tests, same environments, on `main` — 4 failed, 59 passed |
| T11 | AC1 | the fixture writes nothing and reads no path outside `tmp_path` |

## Verification environment

- Python 3.11, `uv` 0.12.17 (the version `.github/workflows/ci.yml` pins, inside the
  `required-version = ">=0.12,<0.13"` window `pyproject.toml` enforces), `uv sync --locked`.
- The two working directories under test: the repository root and `cli/`.
- The two machine states under test: `~/.the-loop/cli-config.yaml` absent, and present as a
  copy of this repository's own `.the-loop/cli-config.yaml` (the ticket's reproduction).
  It carries no credentials; nothing in it is read, since the fixture pins the lookup away
  from it.
- No services, fixtures or credentials are required — the suite never leaves the process.
