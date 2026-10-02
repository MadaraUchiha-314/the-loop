---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#453"
status: in-review            # locked with design.md
approvedBy: []
overrides: {}
riskTier: 3
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: a parked work item is owned by the instance that accepted it

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md). Results
> are recorded in [`evidence/verification.md`](evidence/verification.md).

## What "proved" means here

- A work item this instance armed and parked closes through `close_ticket`, and the
  dispatcher spawns nothing for it afterwards.
- A ref with no record, a record stamped by another instance, and an ended item are
  refused with nothing sent.
- A session-backed close is byte-identical to today's, and a second close is a no-op
  with exit 0.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (guard) | yes | `_accepted_here` through `close_ticket`: a parked record on a named instance closes; an unrelated ref, another instance's record, an unnamed record on a named instance, a named record on an unnamed instance, and an ended item are refused with nothing sent (R1.1, R3.1–R3.3, abuse 1–3) | `tests/test_github_ops.py` |
| T2 | Unit (cancellation) | yes | closing a parked item records `stop` with this instance's name and clears the start mark; the result says `startCancelled`; a second close is exit 0 and records nothing new; a GitHub refusal leaves the item armed; a session-backed close records no stop (R2.1–R2.4, R2.6) | `tests/test_github_ops.py` |
| T3 | Unit (reach) | yes | control-record ownership covers the record's own ref only: `pr merge` of a stranger PR from a parked `--work-item` is refused (R1.3) | `tests/test_github_ops.py` |
| T4 | Integration (dispatcher) | yes | real `Dispatcher` + `ControlStore` + `FakeTmux`: a parked item (start recorded, start-gate parked, no session) is closed through `close_ticket`; the labelled event that follows spawns nothing; a planted record for another instance is refused and the dispatcher's behaviour is unchanged; a session-backed item closes and the daemon's `closed` event ends it (R2.5, R2.6, R3.2, abuse 4) | `tests/test_parked_closure_integration.py` |
| T5 | Negative control | yes | T1, T2 and T4's parked cases fail on the unchanged source | the modules above |
| T6 | Regression (full suite) | yes | green from `cli/`, CI's command | `make test` |
| T7 | Static | yes | `ruff format --check`, `ruff check`, `pyright`, markdownlint | `make lint format-check typecheck` |
| T8 | Contract (OpenAPI) | n/a: the route's body and the response's `additionalProperties: true` object are unchanged; the new field needs no schema edit | | |
| T9 | Manual (live GitHub) | n/a: the close is asserted against the fake client; the real request is `GitHubClient.close_issue`, unchanged since issue-447 | | |
| T10 | UI / visual | n/a: no UI surface | | |
| T11 | Performance | n/a: one small-file read, only after the registry said no | | |

## Scenarios & requirement trace

| Requirement | Rows |
|---|---|
| R1 | T1, T3, T4 |
| R2 | T2, T4 |
| R3 | T1, T4 |
| Abuse 1–4 | T1, T4 |

## Verification environment

This repository's checkout: `uv sync`, then the Makefile targets from the root. No
external services or credentials.

## Activities

- [x] T1–T4 written red first, then green
- [x] T5 recorded
- [x] T6, T7 run from the root

## Verification results

See [`evidence/verification.md`](evidence/verification.md).
