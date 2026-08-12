---
type: testing-plan
phase: test-planning
workItem: issue-217
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: end-to-end PDLC scenario tests

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md),
> before [`tasks.md`](tasks.md). Authored at `test-planning`, completed at
> `verification`. The work item **is** a test suite, so the matrix separates the
> deliverable (the scenarios) from the meta-tests proving the runner itself, and
> from the repo gates that prove the suite integrates.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | End-to-end (the deliverable) | yes | The seven scenarios of R2.3, each walking the shipped `pdlc-work-item-loop` via `Runtime.start/advance/complete` with fixture playback and asserting the full trace (phases, labels, events, locks, execution-log mirror) | `uv run pytest -q cli/tests/test_pdlc_e2e_integration.py` |
| T2 | Unit (runner meta-tests) | yes | `Scenario.load` refusals (missing manifest, unknown step kind, missing fixture — each naming file+field, R2.2); the ordered-subsequence event matcher (match, miss, out-of-order); first-divergence reporting names index/expected/found (R1.4); scenario-dir ↔ named-test consistency (R2.1) | same module |
| T3 | Integration (scenario docstrings) | yes | Every scenario test carries `Feature:`/`Scenario:`/`Requirement:`; the module is discovered by the pinned glob so `the-loop scenarios` tabulates it (R4.1) | `uv run --project cli python -m the_loop scenarios --format table` |
| T4 | Contract (OpenAPI) | n/a — no API surface is touched | | |
| T5 | UI / visual | n/a — no UI is touched | | |
| T6 | Snapshot | n/a — deliberate design absence: expected traces are ordered-subsequence matchers, not golden files, so unrelated new events don't break scenarios | | |
| T7 | Performance / load | yes (bounded, NFR3) | The suite's wall-clock delta is measured at verification and recorded; budget: a few seconds | timing from the pytest run |
| T8 | Security / abuse case | yes | Abuse case 1: unknown step kind refused (T2 rows); abuse case 2: `loop-prevention` scenario positively asserts marked/unauthorized comments never advance a gate; abuse case 3: FakeIntegration raises on unknown operations (asserted in T2) | `uv run pytest -q cli/tests/test_pdlc_e2e_integration.py` |
| T9 | Accessibility | n/a — no user interface | | |
| T10 | Migration / upgrade | n/a — no config key, schema or stored format changes | | |
| T11 | Manual exploratory | n/a — the deliverable is itself an automated walk of the process; there is no live environment whose behaviour the suite doesn't already pin, and no human-only surface (no UI, no service) | | |
| T12 | Docs parity | yes | Capability docs updated in-PR (`testing-and-contracts.md`); docs-parity suite stays green | `uv run pytest -q cli/tests/test_docs_parity.py` |
| T13 | Schema validation | n/a — no schema is touched | | |
| T14 | Lint / format / types | yes | Repo gates, CI parity (ruff, ruff-format, pyright, markdownlint incl. the new README and spec docs) | `make lint format-check typecheck` |
| T15 | Regression (whole suite) | yes | The 1873-test baseline still passes with the new suite added — the e2e harness must not disturb its neighbours (event-log/global-state hygiene: `eventlog.reset()`, graph `_CACHE` untouched because only shipped paths are compiled) | `make test` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1–R1.4, R2.3, R3.1–R3.2 | `happy-path` — full walk, labels/events/locks in order |
| T1 | R2.3 | `trivial-tier` — declared skips recorded as skips, never passes |
| T1 | R2.3 | `ask-reply` — awaiting_input → reply_sent ordering; session-missing reply fails closed (404 contract) |
| T1 | R2.3 | `gate-rejection` — draft artifact blocks; repair advances |
| T1 | R2.3 | `review-rejection` — changes-requested routes backward, label re-enters `loop:design` |
| T1 | R3.3 | `gh-unreachable` — verdict unchanged, `graph.hook_degraded`, events still land |
| T1 | R2.3 | `loop-prevention` — marked + unauthorized comments never release a human gate |
| T2 | R1.4, R2.1, R2.2 | runner refusals + matcher + divergence reporting + dir/test consistency |
| T3 | R4.1 | `the-loop scenarios` lists the new Feature's scenarios |
| T8 | Security 1–3 | abuse-case negatives as above |
| T12 | R4.2 | capability-doc history rows present, parity green |
| T15 | NFR2, NFR4 | whole-suite regression |

## Verification environment

- **Repositories:** this repo only. Each scenario builds its own `tmp_path` git
  checkout (git init + commit — the same plumbing existing integration tests use).
- **Services / containers:** none. No network, no tmux, no `gh`; fakes at the
  `integrations.resolve`, `core_sessions.TmuxRunner`/comment-poster and event-log
  seams (R3.1).
- **Fixtures & data:** the scenario directories themselves
  (`cli/tests/test_pdlc_e2e/scenarios/`), committed with the suite.
- **Credentials:** none.

## Evidence plan

`evidence/verification.md`: per-activity command + outcome, the e2e suite's own
output (scenario list as run), full-suite tail, `the-loop scenarios` output
showing the new rows, lint/type output, and the measured suite runtime (T7).
No screenshots — nothing visual.

## Activities checklist (ticked at `verification`, with results)

- [ ] T1 all seven scenarios green
- [ ] T2 runner meta-tests green (refusals name file+field; divergence names index)
- [ ] T3 `the-loop scenarios` lists the e2e Feature's scenarios
- [ ] T7 suite runtime recorded and within budget
- [ ] T8 abuse-case negatives green
- [ ] T12 docs parity green
- [ ] T14 lint / format / typecheck / markdownlint clean
- [ ] T15 whole suite green (baseline 1873 + new)

## Verification results

Not yet executed.
