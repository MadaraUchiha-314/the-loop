---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#422"
status: in-review            # draft | in-review | approved — locked with bugfix.md
approvedBy: []
overrides: {}
riskTier: 3
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: the suite writes into the checked-in `.the-loop/` when run from the repo root

> Derived from [`bugfix.md`](bugfix.md). Planned at `test-planning`, results recorded at
> `verification` — see [`evidence/verification.md`](evidence/verification.md).

## What "proved" means here

The defect is silent: nothing fails, the tree is just dirty afterwards. A green suite
therefore proves nothing on its own. The plan pairs each run with the state of **both**
`.the-loop/` trees afterwards, ignored files included, from **both** working
directories. It also needs a negative control showing the guard goes red on the unfixed
tree. Without that control, a green guard could equally mean a guard that sees nothing.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Regression (full suite, repo root) | yes | green, and `git status --porcelain --ignored .the-loop cli/.the-loop` is empty afterwards: nothing tracked or ignored was written (AC1, AC2) | `uv run --project cli python -m pytest -q cli` |
| T2 | Regression (full suite, `cli/`) | yes | the same from CI's directory; `cli/.the-loop/` is no longer created (AC2) | `cd cli && uv run python -m pytest -q` |
| T3 | Negative control | yes | with the guard added but the four tests unfixed, the guard fails exactly the four writers (seven cases), naming each path and stack (AC4) | T1 before task A2 |
| T4 | Unit (the guard) | yes | each write shape (`write_text`, append, `os.open`, `mkstemp`, `mkdir`, `unlink`, `os.replace`) is recorded; a read, a write elsewhere and a shared-prefix sibling are not; the report names the writing file; the real guard covers the repository's and the cwd's `.the-loop/` (AC4) | `tests/test_state_isolation.py` |
| T5 | Integration (the four fixed tests) | yes | each passes, and its assertions now hold against what the code wrote: the restart test's log is non-empty, the health test's lock path is the poller's, the doctor's cache is under `<state.root>/local/` (AC2, AC5) | the four modules, plus `test_channels_dm*.py` for the probe's other callers |
| T6 | Static (lint, format, types) | yes | `make lint format-check typecheck` green, markdown included | `make` |
| T7 | Performance | yes | the audit hook costs no measurable wall-clock over the full suite | full suite from `cli/` with and without the hook, same machine, back to back |
| T8 | Contract (OpenAPI) | n/a — no route, parameter or response changed | | |
| T9 | End-to-end (live) | n/a — the one runtime change is a cache path; the doctor integration test drives it through the real command with a fake Slack client | | |
| T10 | UI / visual | n/a — nothing rendered changes | | |
| T11 | Snapshot | n/a — no golden files | | |
| T12 | Security / abuse case | yes | the restart abuse case now reads the log the code writes and still finds no credential; the probe change moves no token; the guard reads nothing | review + T5 |
| T13 | Accessibility | n/a | | |
| T14 | Migration / upgrade | n/a — no key, schema or state format change; an operator's existing cwd-side `slack-directory.json` is simply no longer read, and the cache refetches under the state root | | |
| T15 | Manual exploratory | yes, once | the `sitecustomize` tracer run: every write under either `.the-loop/` from the test process **and** any child inheriting its environment, to establish that the four in-process writers are the whole set | recorded method in the evidence |

## Scenarios & requirement trace

| Row | Acceptance criterion | Scenario / case |
|-----|----------------------|-----------------|
| T1 | AC1, AC2 | root run: green, both trees untouched |
| T2 | AC2 | `cli/` run: green, both trees untouched |
| T3 | AC4 | unfixed tree: seven errors, four tests, each naming its path |
| T4 | AC4 | each write shape recorded; reads and outside writes not |
| T5 | AC2, AC5 | each fixed test green, asserting against the real write |
| — | AC3 | `git ls-files .the-loop/portable` is empty |

## Verification environment

- Python 3.11, `uv` 0.12.17 (inside `pyproject.toml`'s `required-version` window),
  dependencies from `uv sync --all-packages` against the committed `uv.lock`.
- The two working directories: the repository root and `cli/`.
- No home CLI config (`~/.the-loop/` absent). No service, credential or network.

## Activities

- [ ] T3 — negative control on the unfixed tree
- [ ] T1 — full suite from the root, then both trees' status
- [ ] T2 — full suite from `cli/`, then both trees' status
- [ ] T4, T5 — targeted modules
- [ ] T6 — `make lint format-check typecheck`
- [ ] T7 — timing with and without the hook
- [ ] T15 — tracer run, recorded
