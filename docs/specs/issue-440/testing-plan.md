---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#440"
status: in-review            # draft | in-review | approved — locked with design.md
approvedBy: []
overrides: {}
riskTier: 4
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: the harness is a per-work-item choice at `phase-selection`

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md). Results
> are recorded in [`evidence/verification.md`](evidence/verification.md).

## What "proved" means here

- A reply can move a work item onto any offered harness, and onto nothing else.
- The session spawns on the frozen harness, and a forged record falls back to the default.
- Nothing changes for an install with fewer than two hosting harnesses.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (vocabulary) | yes | `hosts_sessions` true for claude and the stub, false for cursor and the base class; `offered_harnesses` keeps declaration order and drops non-hosting/undeclared; `default_harness` honours a hostable `default: true`, skips a non-hosting one, falls back to routing; `config_findings` warns on a non-hosting default (R1.2, R4.1, R4.2) | `tests/test_modelchoice.py` |
| T2 | Unit (gate render) | yes | harness section rendered first with ≥ 2 offered; absent with 0–1 and the body byte-identical to the pre-change one; model/effort rows are the union across offered harnesses (R1.1, R1.3, R2.1, R5.1) | `tests/test_selection_harness.py` |
| T3 | Unit (gate parse) | yes | one tick is a choice; none/two/unoffered is none; a ticked model not offerable on the chosen harness is dropped and named; harness, model and effort land in the result and `frozenGraph`; the confirmation names the harness (R1.4–R1.6, R2.2, R2.3) | `tests/test_selection_harness.py` |
| T4 | Unit (abuse) | yes | an unauthorized reply is ignored; `harness-/bin/sh`, `harness-cursor` (declared, non-hosting), an undeclared name record no choice (abuse 1, 2) | `tests/test_selection_harness.py` |
| T5 | Unit (state) | yes | `harness` round-trips through `WorkItemState`; an old file reads `""`; the runtime freezes it (R1.6, R5.2) | `tests/test_selection_harness.py` |
| T6 | Integration (dispatcher spawn) | yes | real dispatcher over the fake tmux: a frozen harness spawns on that adapter with its own args plus the model; the session record and spawn event name it; a forged/undeclared/non-hosting harness spawns on the default; a respawn keeps the recorded harness (R3.1–R3.4, abuse 3, 4) | `tests/test_dispatcher_harness.py` |
| T7 | Unit (Slack pin) | yes | the Slack mirror's non-phase prefixes include `harness-` | `tests/test_selection_control.py` |
| T8 | Negative control | yes | T2–T6 on the unchanged source fail | the modules above |
| T9 | Regression (full suite) | yes | green from `cli/`, CI's command | `make test` |
| T10 | Static | yes | `ruff format --check`, `ruff check`, `pyright`, config validation, markdownlint | `make lint format-check typecheck validate` |
| T11 | Manual (real harness) | n/a: no second hosting adapter exists to spawn; T6 drives the real dispatcher with two hosting stubs | | |
| T12 | UI / visual | n/a: no UI surface changes | | |
| T13 | Contract (OpenAPI) | n/a: no route or schema changes | | |
| T14 | Performance | n/a: one extra key read from a file already read per spawn | | |

## Scenarios & requirement trace

| Requirement | Rows |
|---|---|
| R1 | T1, T2, T3, T5 |
| R2 | T2, T3 |
| R3 | T6 |
| R4 | T1 |
| R5 | T2, T5, T9 |
| Security abuse cases | T4, T6 |

## Verification environment

Python 3.11 via `uv`, the committed `uv.lock`; no harness binary is executed.

## Evidence to capture

The commands and their summary lines, in `evidence/verification.md`.
