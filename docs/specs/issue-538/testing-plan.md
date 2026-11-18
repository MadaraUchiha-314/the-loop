---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#538"
status: in-review            # design-approval was skipped at phase-selection; the PR approval is the human gate
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: tell the work item's session what happens to its pull-request sessions

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md), before
> [`tasks.md`](tasks.md). Results are filled in below at `verification`.
>
> **This file is executable content.** It names commands an agent will run. No credential,
> network or tmux server is needed: the dispatcher tests use `FakeTmux`, and the graph
> tests use a throwaway git checkout under `tmp_path`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (renderer) | yes | every transition renders the work item, the pull request and the transition; an unknown transition raises; an unknown reason renders `unspecified`; `_identifier()` strips everything outside its class and truncates; the closing line says no pointer moves | `cli/tests/test_prnotice.py` |
| T2 | Unit (gate predicate) | yes | `waits_on_inner_loops` is true for a string spec and a `{hook: …}` mapping, false otherwise; the shipped outer `implementation` node answers true | `cli/tests/test_prnotice.py` |
| T3 | Integration (spawn path) | yes | a spawned endpoint pastes one `spawned` notice into the record's session; each decline (no workspace, workspace failure, shared tree, harness unavailable, hook refusal) and a failed spawn deliver the notice **in the same paste as the event**, ahead of it; each emits exactly one `session.pr_notice_*` | `cli/tests/test_pr_notices_integration.py` |
| T4 | Integration (close path) | yes | a merged endpoint that had a session → one `merged` notice; closed unmerged → one `closed` notice naming the outer node and, when it waits on `await-inner-loops`, that it will keep waiting; an endpoint with no `tmux_target` → no notice; a paused record → `skipped(paused)`; no record session → `skipped(no-live-session)`; a failing paste → `failed`, and the close path still closes the endpoint | same |
| T5 | Integration (outer re-evaluation) | yes | a real outer graph parked at `implementation` (all tasks ticked, one inner loop) advances to `verification` when its pull request merges, with no claim and no further event; not parked → untouched; parked on a node without the gate → untouched; a second pending inner loop → still waits; closed-unmerged → no re-evaluation; `graph.outer_reevaluated` recorded each time | same, plus `cli/tests/test_graph_multirepo_integration.py` style fixture |
| T6 | Integration (inner advance) | yes | an approval classified on the endpoint's `pr-approval` gate moves the inner loop to `complete` → one `completed` notice and an outer re-evaluation; an inner advance reporting `escalated` → one `escalated` notice naming the inner node | `cli/tests/test_pr_notices_integration.py` |
| T7 | Integration (respawn path) | yes | a dead endpoint respawned → `respawned` notice; a respawn whose harness is unavailable → `respawn-failed` notice; the record's own respawn sends none | same |
| T8 | Security / abuse case | yes | abuse 1: a merge whose PR title, body and branch carry an instruction string → absent from every paste; abuse 2: closed-unmerged leaves the outer `work-item-state.json` byte-identical; abuse 3: an unlinked PR's close → no paste, no re-evaluation; abuse 4: the same merge delivered twice → one notice | same |
| T9 | Regression | yes | the existing issue-172 test that asserted no delivery on a linked PR's merge now asserts exactly the one `merged` notice; the full suite stays green | `cli/tests/test_webhook_routing_integration.py`, `make test` |
| T10 | Static (lint, format, types) | yes | `ruff check`, `ruff format --check`, `pyright`, markdownlint on the changed docs | `make lint`, `make format-check`, `make typecheck` |
| T11 | Contract (OpenAPI) | n/a | no API route, request or response changes | — |
| T12 | E2E (real tmux + GitHub) | n/a | the paste is `TmuxRunner.deliver`, already covered by its own tests; driving a real merge needs a live repository and is what the dispatcher tests stand in for. The ticket's own reproduction is exercised by T5 against the shipped graph | — |
| T13 | UI / visual / snapshot / accessibility | n/a | no user-facing surface | — |
| T14 | Performance | n/a | one paste and at most one exit-chain run per transition; no loop, no polling | — |
| T15 | Migration | n/a | no persisted format changes; existing state files are read unchanged | — |
| T16 | Manual | n/a | every behaviour is observable through `FakeTmux` and the event log | — |

## Scenarios & requirement trace

| Requirement | Rows |
|---|---|
| R1.1 spawned | T3 |
| R1.2 declined (five reasons) | T3 |
| R1.3 spawn-failed | T3 |
| R1.4 one paste with the event | T3 |
| R1.5 merged / completed | T4, T6 |
| R1.6 closed, names the waiting gate | T4 |
| R1.7 escalated | T6 |
| R1.8 respawned / respawn-failed | T7 |
| R1.9 one event per notice | T3, T4, T6, T7 |
| R2.1 re-evaluate on merge | T5 |
| R2.2 re-evaluate on inner complete | T6 |
| R2.3 only when parked on an `await-inner-loops` node | T5, T2 |
| R2.4 pass → next assignment delivered | T5 |
| R2.5 wait/block recorded, no retry | T5 |
| R2.6 no re-evaluation on close-unmerged | T5, T8 |
| R3.1–R3.3 paused / absent / paste failure | T4 |
| R3.4 state readable as today | T4 (inner state file asserted) |
| R3.5 re-evaluation fault contained | T5 (a raising runtime factory) |
| R4.1–R4.2 one-way rule | T5, T8 |
| R4.3 never posted to a thread | T4 (the fake GitHub client records no comment) |
| Abuse cases 1–4 | T8 |

## Verification environment

- **Repository:** this checkout, branch `the-loop/issue-538-pr-session-notices`.
- **Toolchain:** `uv sync` (Python per `uv.lock`), Node for `npx markdownlint-cli2`.
- **Services:** none. `FakeTmux` stands in for tmux; the graph tests create a git checkout
  with an `origin` remote under `tmp_path`.
- **Credentials:** none.
- **Bring-up:** `make install-dev`.

## Evidence plan

- `evidence/verification.md` — per command: the command, the exit status and the tail of
  its output in fenced blocks (pytest summary lines, ruff/pyright summaries).
- The red→green transition for T4/T5/T9: the new tests' failing run before the
  implementation, recorded in the same file.
- Nothing to redact: no credentials, hostnames or personal data appear in test output; the
  file is checked for them before commit.

## Verification activities

- [ ] V1 — `cd cli && uv run python -m pytest -q tests/test_prnotice.py tests/test_pr_notices_integration.py` (T1–T8)
- [ ] V2 — `cd cli && uv run python -m pytest -q tests/test_webhook_routing_integration.py tests/test_graph_multirepo_integration.py tests/test_graph_loops.py` (T9 and neighbours)
- [ ] V3 — `make test` (full suite, T9)
- [ ] V4 — `make lint && make format-check && make typecheck` (T10)
- [ ] V5 — `uv run the-loop scenarios --glob 'cli/tests/test_pr_notices_integration.py'` lists every new scenario with its requirement link

## Verification results

_Filled in at `verification`._

## Review comments
