---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#270"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: name the third fate of a delivery id

> Derived from the approved `bugfix.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `Deduper`'s outcome value (set, read, evict, discard), the five settlement sites, `delivery_status` precedence, `delivery_outcome`, the poller's two settlement branches, `gaveUp` untouched, no give-up notice, the presence branch | `make test` (`uv run pytest cli/tests`) |
| T2 | Integration (scenario) | yes | the reproduction end to end on the poll ingress — several cycles, a simulated restart, and an upgrade that re-arms nothing — Gherkin-documented | `make test` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — the control-plane API is untouched: no path, schema or response shape changes, and the poll ledger is not exposed through it | | |
| T4 | End-to-end | n/a — an E2E run needs a real GitHub repository, a real `gh` credential and a real tmux/harness; T2 drives the real `Dispatcher` and the real `PollState` against injected tmux/provider fakes, which is how this path has always been proved in this repo | | |
| T5 | UI / visual | n/a — no user-facing surface; the change is daemon-internal accounting plus documentation | | |
| T6 | Snapshot | n/a — no rendered artefact changes. The two prompt templates *do* change, and the existing byte-identical parity test (`test_interaction.py`) is the guard that they change together | | |
| T7 | Performance / load | n/a — the change removes per-cycle work (a settled comment stops being re-evaluated) and adds one string per live dedup entry. There is nothing to measure that would rise above noise | | |
| T8 | Security / abuse case | yes | the muting direction: a *deliverable* comment is never baselined — `done` outranks a settlement, and a failed dispatch still retries. Plus: no comment text enters the record | `make test` |
| T9 | Accessibility | n/a — no user interface | | |
| T10 | Migration / upgrade | yes | an existing deployment's ledger: a comment stuck at `commentAttempts: 1` from a previous version is resolved on the next cycle, and a comment already in `gaveUp` is **not** re-armed into a late replay | `make test` |
| T11 | Manual exploratory | n/a — the reproduction is a multi-cycle poll against a fake provider; mechanised as T2, which is stricter (it asserts the on-disk ledger, not the observed symptom) | | |
| T12 | Static analysis (lint + types) | yes | `ruff`, `pyright`, `markdownlint` over the changed modules and docs | `make lint` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.5 | `Deduper` stores an outcome beside the mark; `discard` and LRU eviction remove both; `mark_settled` on an unknown id marks it |
| T1 | R1.1 | each settlement site records its outcome: `awaiting-start`, `session-paused` (both the synchronous and the pre-dispatch case), `control-executed`, `control-rejected`, `control-ambiguous` |
| T1 | R1.2 | `delivery_status` answers `settled`, and `delivery_outcome` names the outcome |
| T1 | R1.3 | a delivery recorded by a session outranks a settlement on another endpoint (`done`) |
| T1 | R1.4 | `spawn-policy` still releases the id (`unhandled`); `session-occupied`, `session-vanished`, `work-item-not-found` and `dispatch.failed` are unchanged |
| T1 | R2.1, R2.2 | a synchronously settled comment is baselined with **no** attempt recorded and no `poll.comment_forwarded` |
| T1 | R2.3 | a comment settled after an attempt was recorded is resolved on the next cycle, and `commentAttempts` is cleared |
| T1 | R2.4 | `gaveUp` gains nothing, so `rearm_gave_up_comments` re-arms nothing |
| T1 | R2.5 | no give-up notice is posted for a settled comment |
| T1 | R2.6 | a settled presence delivery resets the spawn ledger instead of spending the budget |
| T1 | R2.7 | `poll.comment_settled` carries work item, comment, actor, outcome, `will_retry: false` |
| T1 | R3.4 | the event catalogue holds `poll.comment_settled` (the emitted-vs-catalogued parity test) |
| T1 | R3.3 | both spawn-prompt copies tell the session to read the whole thread, and stay byte-identical |
| T2 | R2.1, R2.2, R2.3, R2.5 | `Scenario: a comment made before the start is refused once and never counted again` — three cycles plus a restart, and no give-up notice posted |
| T10 | R2.1, R2.4 | `Scenario: an upgrade does not replay a comment that was refused before the start` — a ledger already stuck at `commentAttempts: 1`, plus a comment an older version abandoned |
| T8 | Security design | `test_a_delivery_a_session_received_outranks_a_settlement` (a delivered comment is never baselined as settled) and `test_a_spawn_policy_drop_still_releases_its_id_and_settles_nothing` (a refusal that wants a retry still gets one) |
| T12 | R4 | lint and type checks pass over the changed modules |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. No tmux, no harness, no network: the dispatcher's tmux
  runner and the poller's provider are injected fakes, as in `cli/tests/test_routing.py`,
  `cli/tests/test_poller.py` and `cli/tests/test_poller_integration.py`.
- **Fixtures & data:** the existing dispatcher/poller fixtures; `tmp_path` for the state root
  so the portable record is asserted on disk.
- **Credentials:** none. No `gh` is invoked: the give-up notice's runner is injected
  (`comment_runner`, as in the existing issue-240 tests) and the assertion is that the code
  path which would post it is never reached.
- **Bring-up:** `make test` · **Tear-down:** none (pytest `tmp_path`).
- **If bring-up fails:** record it under Verification results, leave the dependent activities
  unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T10 | red run — the new tests, run before any production code changed | `red.md` |
| T1, T2, T8, T10 | green run — full suite summary and the per-file runs | `unit-and-integration.md` |
| T12 | `make lint` / type-check output | `lint-and-typecheck.md` |
| — | security review record (checklist per `reference/security.md`) | `security-review.md` |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_routing.py cli/tests/test_poller.py cli/tests/test_eventlog.py cli/tests/test_interaction.py`
- [x] T2, T10 — `uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py`
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests/test_routing.py cli/tests/test_poller.py -k "settle or settled"`
- [x] T12 — `make lint` (`ruff check`, `ruff format --check`, `markdownlint-cli2`) and `uv run pyright cli`
- [x] Full suite — `make test`
- [x] Red run captured before the fix — `evidence/red.md`
- [x] Security review — the checklist in `reference/security.md`, against the diff

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|---|---|---|---|
| Red run | the 17 new tests, written and run **before** any production code changed | 17 failed, 0 passed — including the two controls, which fail only on the missing `delivery_outcome` accessor and pass on the pre-change *behaviour* | [`evidence/red.md`](evidence/red.md) |
| T1 | `pytest -q cli/tests/test_routing.py cli/tests/test_poller.py cli/tests/test_eventlog.py cli/tests/test_interaction.py` | 351 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T2, T10 | `pytest -q cli/tests/test_poller_integration.py` | 24 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T8 | `pytest -q cli/tests/test_routing.py cli/tests/test_poller.py -k "settle or settled"` | 14 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| Full suite | `make test` | **2476 passed, 1 skipped** after rebasing onto `main` at `ede4630`; 18 of them this work item's (17 red-first, 1 added in self-review). Pre-rebase, on `main` at `fc3adcf`: 2428 passed, 1 skipped, up from 2410 | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T12 | `uv run ruff check cli hooks`, `uv run ruff format --check cli hooks`, `uv run pyright cli`, `markdownlint-cli2` (817 files), `scripts/validate_config.py` | clean on the first run of each | [`evidence/lint-and-typecheck.md`](evidence/lint-and-typecheck.md) |
| Security review | checklist (`reference/security.md`), effective risk tier 3 | pass, no unresolved findings | [`evidence/security-review.md`](evidence/security-review.md) |

Every planned activity ran. Nothing was replanned, and nothing is left unticked.
