---
type: tasks
phase: tasks-breakdown
workItem: "issue-315"
status: draft
approvedBy: []
overrides: {}
---

# Tasks: one repository's failure is that repository's

> Phase 3 of 3. Small, verifiable tasks; each `_Test:_` names a row of `testing-plan.md`.

## Task list

- [x] 1. The contract: `Listing`, `ScopeFailure`, `listing()`, `scope_of()`
  - `cli/the_loop/poller/base.py`; re-exported from `poller/__init__.py`.
  - _Depends on:_ none
  - _Requirements:_ R1.4
  - _Test:_ `T2`

- [x] 2. The GitHub provider lists per repository and quarantines disabled Issues
  - `cli/the_loop/poller/github.py`: `listing`, `_list_scope`, the `_issues_off`
    ledger and re-probe, `scope_of`, `list_work_items` as the strict form.
  - Security-relevant (A2, A3): issues only are withheld; one exact message classifies.
  - _Depends on:_ 1
  - _Requirements:_ R1.1, R2.1–R2.4
  - _Test:_ `T1`

- [x] 3. The core consumes the listing, records per scope, reconciles per scope
  - `cli/the_loop/poller/poller.py`: `_poll_provider`, `_reconcile_closures(…,
    degraded)`, `PollSummary` fields, the cycle log line; `eventlog.py` catalogue
    entries for `poll.scope_error`, `poll.scope_degraded`, `poll.scope_recovered`.
  - Security-relevant (A4): a degraded scope's sessions are never asked about closure.
  - _Depends on:_ 1
  - _Requirements:_ R1.1–R1.3, R2.1, R2.3
  - _Test:_ `T2, T5`

- [x] 4. The heartbeat carries the scopes and `status` renders them
  - `cli/the_loop/poller/heartbeat.py` (`_counters`), `cli/the_loop/poller/daemon.py`
    (`heartbeat_lines`).
  - _Depends on:_ 3
  - _Requirements:_ R3.1–R3.4
  - _Test:_ `T3`

- [x] 5. The integration scenario
  - `cli/tests/test_poller_integration.py`: a two-repository `gh` double through the
    ticket's sequence.
  - _Depends on:_ 2, 3
  - _Requirements:_ R4.1
  - _Test:_ `T4`

- [x] 6. Docs, capability docs, decision, execution log, evidence
  - `docs/config/cli/polling-options.md`, `docs/cli/commands/status.md`,
    `docs/cli/state.md`, `docs/capabilities/cli.md`, `docs/decisions/decision-106.md`
    (+ index), `docs/specs/issue-315/execution-log.md`, `evidence/`.
  - _Depends on:_ 1–5
  - _Requirements:_ all
  - _Test:_ `T6, T7 — make check`
