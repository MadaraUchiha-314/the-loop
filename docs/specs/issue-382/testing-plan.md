---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#382"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
riskTier: 3
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: the poll clocks are this machine's, not the repository's

> Derived from the approved `requirements.md` and `design.md`, **before** `tasks.md` —
> each task's `_Test:_` names a row of the matrix below. Authored at `test-planning` and
> completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit — the store | yes | `PollClockStore` round-trips, and degrades to an empty map on every fault (absent, malformed, unwritable) | `uv run --project cli python -m pytest -q cli/tests/test_pollclocks.py` |
| T2 | Unit — the split | yes | the poller writes clocks locally and never into the portable record; a quiet cycle rewrites no record; the closure schedule reads the local clocks | `uv run --project cli python -m pytest -q cli/tests/test_poller.py` |
| T3 | Unit — the readers | yes | `sessions reset` drops the clocks; the control plane still serves them | `uv run --project cli python -m pytest -q cli/tests/test_reset.py cli/tests/test_core_workitems.py` |
| T4 | Integration (scenario) | yes | a restarted poller does not re-ask about an item it just polled, and the tracked record it leaves behind holds no timestamp | `uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py` |
| T5 | Migration / upgrade | yes | a record written by an earlier version keeps its schedule and is stripped on the next write | `uv run --project cli python -m pytest -q cli/tests/test_poller.py -k upgrade` |
| T6 | Contract (declaration ↔ docs ↔ `.gitignore`) | yes | the new path is classified local, documented as local, and ignored by the published recipe | `uv run --project cli python -m pytest -q cli/tests/test_state_portability.py` |
| T7 | Security / abuse case | yes | a forged-future clock defers rather than acts; a malformed clock reads as *no clock*; a write failure never fails a cycle | `uv run --project cli python -m pytest -q cli/tests/test_pollclocks.py -k "future or malformed or unwritable"` |
| T8 | Full suite + lint + types | yes | nothing else in the CLI depended on the moved keys | `make check` |
| T9 | End-to-end (a live poller against GitHub) | n/a — the poll loop's provider is already faked at the boundary by the integration suite; a live run would prove the provider, which this change does not touch | |
| T10 | UI / visual | n/a — the served record's shape is unchanged, so no rendered surface changes | |
| T11 | Snapshot | n/a — no rendered output or generated file is snapshotted in this repo | |
| T12 | Performance / load | n/a — the change strictly removes writes (one small file instead of *n* records + index per cycle); no latency-sensitive path is touched | |
| T13 | Accessibility | n/a — no user interface | |
| T14 | Manual exploratory | yes | the dogfood: run `poll --once` against this repository's own `state.root` twice and confirm `git status` stays clean | manual, recorded under Verification results |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R2.5 | a put/get round-trip; an absent file; a file of garbage; a directory that cannot be written |
| T2 | R1.1, R1.2, R1.3, R1.4, R1.6 | `finalize` stamps the local file and leaves the record clock-free; `baseline_comments` likewise; `note_closure_check` likewise; a pull request's ledger keyed by its own ref; a cycle that learns nothing writes no record |
| T2 | R2.1 | the ledger-only closure schedule is due/not-due on the local clocks, with the window and cap unchanged |
| T3 | R1.5 | `reset_work_item` leaves no clock for the ref it reset |
| T3 | R2.4 | `list_work_items` / `get_work_item` return `poll.lastPolledAt` and each pull request's, merged from the local file |
| T4 | R1.1, R2.1 | `Scenario: a restarted poller does not re-ask about an item it polled a moment ago` |
| T5 | R2.2, R2.3 | a record carrying `poll.lastPolledAt` from an earlier version is read for the schedule, then written back without it |
| T6 | R3.1, R3.2, R3.3 | the portability suite's S1–S5 over the new path |
| T7 | Abuse 1–3 | a future clock is not due; a malformed clock reads as no clock; an unwritable file logs and continues |
| T14 | R1.1, R1.6 | the working tree stays clean across poll cycles in the-loop's own checkout |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. The poll suites drive a fake `PollProvider`; no network,
  no `gh`, no tmux.
- **Fixtures & data:** `tmp_path` state roots built by the existing poller fixtures.
- **Credentials:** none — this change reads and writes no credential.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1–T3, T5–T7 | per-suite run output (counts, duration) | `unit.md` |
| T4 | the scenario's Gherkin docstring and its run output | `integration.md` |
| T8 | `make check` output | `final-validation.md` |
| T14 | the `poll --once` transcript and the `git status` before/after | `final-validation.md` |

## Verification activities

- [ ] T1 — `uv run --project cli python -m pytest -q cli/tests/test_pollclocks.py`
- [ ] T2 — `uv run --project cli python -m pytest -q cli/tests/test_poller.py`
- [ ] T3 — `uv run --project cli python -m pytest -q cli/tests/test_reset.py cli/tests/test_core_workitems.py`
- [ ] T4 — `uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py`
- [ ] T5 — `uv run --project cli python -m pytest -q cli/tests/test_poller.py -k upgrade`
- [ ] T6 — `uv run --project cli python -m pytest -q cli/tests/test_state_portability.py`
- [ ] T7 — `uv run --project cli python -m pytest -q cli/tests/test_pollclocks.py -k "future or malformed or unwritable"`
- [ ] T8 — `make check`
- [ ] T14 — two `poll --once` cycles against this checkout's own `state.root`, with `git status` before and after

## Verification results

_Not yet executed._

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
