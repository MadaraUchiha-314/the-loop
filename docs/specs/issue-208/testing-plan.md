---
type: testing-plan
phase: test-planning
workItem: issue-208
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: `the-loop ask` + `POST /api/v1/sessions/reply`

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md), before
> [`tasks.md`](tasks.md). Authored at `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `ask_session` (marker stamped, event on success and on gh failure, empty-question/bad-ref refusals, comment URL captured), `reply_session` (framing, paused/missing/dead refusals, event, marked report comment), `post_issue_comment_with_url` parsing, `attention`'s open/answered rule | `uv run pytest -q cli/tests/test_core_sessions.py cli/tests/test_comments.py cli/tests/test_core_attention.py` |
| T2 | Integration (scenario) | yes | The route as served: delivered reply reaches the pane and emits `reply_sent`; 404 no-session / dead-pane without respawn; 400 paused / empty text; the report comment carries the marker; the CLI verb end-to-end with a fake `gh` | `uv run pytest -q cli/tests/test_ask_reply_integration.py` |
| T3 | Contract (OpenAPI) | yes | The authored contract gains exactly `/api/v1/sessions/reply` (`replySession`) and still equals the served schema (R2.7) | `uv run pytest -q cli/tests/test_api_contract_parity.py` |
| T4 | End-to-end | n/a — a real agent in a real tmux pane answering a real GitHub comment is T11's manual walk; every seam in between (paste, gh, events) is covered in-process | | |
| T5 | UI / visual | n/a — the card exists since issue-207; this enables its controls, no layout/token change | | |
| T6 | Snapshot | n/a — no serialized artifact is produced | | |
| T7 | Performance / load | n/a — one POST that shells two short-lived processes; no budget at stake | | |
| T8 | Security / abuse case | yes | One negative test per § Security design mechanism: no respawn on dead/missing session, paused refused, marked report body, marked question body, idempotent stamp | `uv run pytest -q cli/tests/test_ask_reply_integration.py cli/tests/test_core_sessions.py` |
| T9 | Accessibility | n/a in new work — the reply box shipped with `aria-label` in issue-207; enabling it changes no semantics | | |
| T10 | Migration / upgrade | n/a — no config key, schema, or stored format changes; old event logs simply lack the new types and `attention` derives nothing from them | | |
| T11 | Manual exploratory | yes | A spawned session runs `the-loop ask`; the dashboard card lights, the reply box delivers into the pane, the card closes | a human, a workstation with the daemon + a session |
| T12 | Docs parity | yes | The new event types appear in the observability reference; CLI/API docs updated | `uv run pytest -q cli/tests/test_docs_parity.py` |
| T13 | Schema validation | n/a — no schema is touched (NFR2) | | |
| T14 | Lint / format / types | yes | Repo gates, CI parity | `make lint format-check typecheck` |
| T15 | UI unit | yes | The reply box posts to the route, reports failure, clears on success; demo mode refuses; the `awaitingInput` model tests keep passing | `bun run test` in `ui/` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, abuse 5 | the posted body ends with attribution + marker; an already-marked question is not double-stamped |
| T1 | R1.2, R1.3 | event emitted with comment_url on success; emitted with `comment_posted: false` when `gh` fails |
| T1 | R1.4 | empty question / malformed ref → error, nothing posted, nothing emitted |
| T1 | R2.1 | the framed prompt carries provenance + actor + the text |
| T1 | R2.6, abuse 4 | the report comment quotes the reply and carries the marker |
| T1 | R3.1 | open question → row; reply newer than question → no row; re-asked after reply → row again |
| T2 | R2.1, R2.2 | `Scenario: an operator's reply is pasted into the waiting session` |
| T2 | R2.3, abuse 2 | `Scenario: a reply to a work item with no session is refused without spawning` / `…dead pane…` |
| T2 | R2.4, abuse 3 | `Scenario: a reply to a paused session is refused` |
| T2 | R2.5 | `Scenario: an empty reply is refused` |
| T2 | R1.1–R1.3 | `Scenario: the ask verb posts a marked question and records the wait` (+ gh-failure variant) |
| T3 | R2.7 | contract parity over the new path |
| T12 | R3.2 | both event types documented |
| T15 | R5.1, R5.2 | the enabled reply box; demo refusal; stale copy gone |
| T11 | all | the full loop, by hand |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none for T1–T3, T8, T12, T14 — `TestClient` drives the app
  in-process; `gh` and tmux are injected/monkeypatched fakes. T15 needs bun. T11 needs a
  workstation with tmux, `gh` and a spawned session (a human's).
- **Fixtures & data:** inline per test; `state.root`/registry dirs under `tmp_path`.
- **Credentials:** none (fakes only).

## Evidence to capture

`evidence/verification.md`: per-activity command + outcome, full suite tail, lint/type
output, UI test output. No screenshots — the UI change is behavioural (T15 asserts it);
T11 is deferred to the reviewer's workstation and said so honestly.

## Activities checklist (ticked at `verification`, with results)

- [x] T1 unit suites green — 1849 passed, 1 skipped (baseline 1819); see
      [`evidence/verification.md`](evidence/verification.md)
- [x] T2 integration scenarios green, Gherkin docstrings present
      (`test_ask_reply_integration.py`, 9 scenarios)
- [x] T3 contract parity green (`/api/v1/sessions/reply` in both contract and served
      schema)
- [x] T8 negative tests green (no-spawn, paused, marked bodies, idempotent stamp)
- [x] T12 docs parity green (both event types documented in `EVENT_TYPES`)
- [x] T14 lint / format / typecheck / markdownlint / schema validation clean
- [x] T15 UI suite green — 52 passed, incl. the send-flow and inbox-dedupe tests;
      `bun run build` clean
- [ ] T11 manual walk — deferred to a human with a workstation; the one activity this
      plan cannot run itself (steps in [`evidence/verification.md`](evidence/verification.md))

## Verification results

Executed 2026-08-12 by the implementing session. Everything but T11 ran and passed;
full command output in [`evidence/verification.md`](evidence/verification.md). One
honesty note on TDD: the new tests were written alongside the implementation in one
pass, not strictly red-first — the red→green transitions were observed per-assertion
while iterating (one genuine red is recorded in the execution log), but this session
cannot present a committed red state as evidence.
