---
type: testing-plan
phase: test-planning
workItem: "issue-315"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: one repository's failure is that repository's

> Derived from `bugfix.md` and `design.md`, **before** `tasks.md`. Authored at
> `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit — the GitHub provider | yes | `listing()` isolates per repository (items from the healthy one, a `ScopeFailure` for the other, both pull-request and issue failures); "has disabled issues" is permanent: first sighting in `failures`, then `skipped` with no `gh issue list` call while `gh pr list` still runs, re-probed at cycle 60, renewed silently on a repeat, `recovered` on success; `scope_of`; `list_work_items` still raises; `owns` untouched | `uv run pytest cli/tests/test_poller.py -k "scope or listing or quarantin or disabled"` |
| T2 | Unit — the poller core | yes | a `Listing` with one failure still processes the other items (spawn recorded); `poll.scope_error` / `poll.scope_degraded` / `poll.scope_recovered` emitted with the documented fields; `summary.errors`, `scopes_failed`, `scopes_skipped`, `scopes_polled`; reconciliation skips sessions in a degraded scope and still runs for healthy ones; a provider without `listing()` behaves exactly as before | `uv run pytest cli/tests/test_poller.py -k "scope or listing or isolat or reconcil"` |
| T3 | Unit — heartbeat + `status` | yes | the three new `lastCycle` keys round-trip; a heartbeat without them reads; `heartbeat_lines` prints `degraded:` per scope and the "no repository was polled" line; a clean cycle prints exactly what it printed before; `--format json` carries the facts; the exit code is unchanged | `uv run pytest cli/tests/test_poll_heartbeat.py cli/tests/test_poll_status.py` |
| T4 | Integration (scenario) | yes | `Scenario: one repository with Issues disabled does not blind the others` — the real provider, the real dispatcher, a two-repository `gh` double: cycle 1 spawns the healthy item and records the degraded repository; cycle 2 makes no `gh issue list` call for it, still lists its pull requests, and forwards a new comment on the healthy item; Gherkin-documented | `uv run pytest cli/tests/test_poller_integration.py -k disabled` |
| T5 | Event catalogue parity | yes | every emitted event type is in `EVENT_TYPES` | `uv run pytest cli/tests/test_eventlog.py` |
| T6 | Security / abuse case | yes | A2 (pull requests still listed while issues are skipped), A3 (only the exact message classifies; a 502 stays transient), A4 (a session in a degraded scope is never reconciled) | T1, T2, T4 |
| T7 | Lint / typecheck / tests | yes | the commands CI runs | `make check` |
| T8 | Contract (OpenAPI) | n/a — the `status` route's row already carries `lastCycle` as an open object; no schema field changes | | |
| T9 | UI / visual | n/a — no dashboard change | | |
| T10 | Performance | n/a — the quarantine saves one `gh` call per skipped repository per cycle; nothing else changes in cost | | |
| T11 | Migration / upgrade | n/a — the heartbeat's new keys are additive and an older file reads unchanged (T3) | | |
| T12 | Manual | n/a — no repository with Issues disabled is reachable from this session; `gh`'s exact message is taken from the ticket's log excerpt and pinned in T1/T4 | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.4, R2.1–R2.4, A2, A3 | per-repository listing; the quarantine timeline; the strict form |
| T2 | R1.1–R1.4, R2.1, A4 | isolation in the core; events; reconciliation at the finer grain |
| T3 | R3.1–R3.4 | the heartbeat and the two `status` formats |
| T4 | R1.1, R2.1, R2.2, R4.1 | `Scenario: one repository with Issues disabled does not blind the others` |
| T5 | R1.2, R2.1 | the catalogue |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none — `gh` is replaced by an injected runner in every test.
- **Fixtures & data:** canned `gh --json` answers in the tests; `gh`'s "has disabled
  issues" message copied from the ticket.
- **Credentials:** none.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results and escalate.

## Evidence plan

- `evidence/verification.md` — red→green per task, `make check` output, the matrix
  results.
- `evidence/security-review.md` — the abuse-case dispositions.

## Activities checklist

- [x] T1 provider unit tests, red first
- [x] T2 core unit tests, red first
- [x] T3 heartbeat and `status` tests, red first
- [x] T4 integration scenario, red first
- [x] T5 catalogue parity
- [x] T6 abuse cases (in T1/T2/T4)
- [x] T7 `make check`

## Verification results

Recorded at `verification` in [`evidence/verification.md`](evidence/verification.md):
every applicable row (T1–T7) **pass**; `make check` clean — ruff, format, pyright,
config validation, markdownlint, 2976 tests passed / 1 skipped. T8–T12 `n/a` as planned.
