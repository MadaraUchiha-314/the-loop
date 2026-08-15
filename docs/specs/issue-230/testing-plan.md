---
type: testing-plan
phase: test-planning
workItem: issue-230
status: draft                # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: a readable session stream, a session tree, and a chat bar

> Derived from `requirements.md` and `design.md`, **before** `tasks.md`. Authored at the
> `test-planning` node and **completed at the `verification` node**.
>
> **This file is executable content.** It names commands an agent will run; every
> command runs a test suite or a linter over this repository. No credentials involved.

## What this work item has to prove

1. **No line renders blank.** The projection is fed every shape the issue names —
   `tool_result` entries above all — plus the shapes that were already silently blank
   (thinking, summary/system, unknown), and each asserts a non-empty, labelled row or a
   pairing (R1).
2. **Pairing is by id, not by adjacency.** Results attach to the call with the matching
   `tool_use_id`, across interleaved calls, and an orphan result still renders (R1.1,
   R1.2).
3. **A PR ref's reply lands in the PR's pane.** The service test registers a record with
   a PR endpoint and asserts delivery targeted the endpoint's tmux target — and that
   every issue-208 refusal still refuses (R4.2, R4.3).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit — projection | yes | `transcriptThread`: pairing by `tool_use_id` (string + block results, interleaved calls), orphan results as rows, thinking captured, meta labelling for summary/system/unknown, malformed passthrough, per-tool summaries incl. unknown-tool fallback (R1, R2.1) | `cd ui && bun run test` (`model.test.ts`) |
| T2 | Unit — sidebar join | yes | `sessionTree`: two-level tree per work item, PR endpoints as children, ad-hoc/contribution items flagged treeless (R3.2, R3.3) | `cd ui && bun run test` (`model.test.ts`) |
| T3 | Component — stream | yes | `TranscriptView` renders collapsed `<details>` per tool call with summary + error tag, expanded user/assistant text; `ChatBar` disabled states and successful send calling `replySession` with the viewed ref (R2, R4.1, R4.4) | `cd ui && bun run test` (`Transcript.test.tsx`) |
| T4 | Integration — reply route | yes | `POST /api/v1/sessions/reply` with a PR ref delivers into the PR endpoint's pane; a closed PR endpoint falls back to the record's session; paused record still 400s; unknown ref still 404s (R4.2, R4.3) | `uv run pytest cli/tests/test_ask_reply_integration.py` |
| T5 | Unit/regression — whole suites | yes | nothing else regressed | `uv run pytest cli` and `cd ui && bun run test` |
| T6 | Lint + types | yes | ruff, pyright, oxlint, `tsc --noEmit`, markdownlint over changed docs | `make lint` equivalents; `cd ui && bun run lint && bun run typecheck` |
| T7 | Contract | yes | the OpenAPI description of `/sessions/reply` matches the new resolution behaviour (prose change; shapes untouched) | review of `docs/api-specs/openapi/the-loop.v1.yaml` |
| T8 | UI/visual | yes | the Sessions screen and collapsed stream rendered against the demo fixture; screenshots committed as evidence | `cd ui && bun run dev` + browser capture |
| T9 | e2e | n/a | needs a live tmux + harness workstation; the seams it would cover (route → registry → tmux) are covered by T4 against a fake runner, and the UI side by T3 against the demo transport | — |
| T10 | Performance | n/a | the projection is linear over ≤ the served tail (bounded by the route's `tail` param); no new polling | — |
| T11 | Security/abuse | yes | T1 includes markup-bearing tool text asserted to render as text (React escaping); T4 includes the fail-closed refusals | within T1/T4 |
| T12 | Accessibility | yes | disclosure uses native `<details>/<summary>`; chat bar keeps labelled controls (checked in T3 via roles/labels) | within T3 |
| T13 | Migration | n/a | no stored shape changes; registry records and transcript files are read as-is | — |
| T14 | Manual | yes | demo-fixture walkthrough of sidebar → tree → stream → chat bar | recorded in evidence |

## Verification environment

This repository alone: `uv` for the Python suite, `bun` for the UI suite, both already
pinned by the repo. The reply-route test uses the existing fake-tmux seam in
`cli/tests` (no real tmux). Browser capture for T8 uses the bundled demo fixture — no
service, no network.

## Evidence to capture

`docs/specs/issue-230/evidence/`: full-suite output (markdown, fenced), and screenshots
of the Sessions screen (sidebar + tree), a collapsed stream, an expanded tool call, and
the chat bar states.

## Verification record

Completed at the `verification` node — see the execution log entry for this phase.

| # | Ran | Outcome | Evidence |
|---|-----|---------|----------|
| T1 | `cd ui && bun run test` | pass — 104 tests across 7 files, 0 failures (7 `transcriptThread` cases) | [`evidence/full-suite.md`](evidence/full-suite.md) |
| T2 | `cd ui && bun run test` | pass — same run (2 `sessionTree` cases) | [`evidence/full-suite.md`](evidence/full-suite.md) |
| T3 | `cd ui && bun run test` | pass — same run (`Transcript.test.tsx`, 7 tests) | [`evidence/full-suite.md`](evidence/full-suite.md) |
| T4 | `uv run pytest cli/tests/test_ask_reply_integration.py` | pass — 13 tests incl. 4 new PR-endpoint scenarios | [`evidence/full-suite.md`](evidence/full-suite.md) |
| T5 | `uv run pytest cli` + `cd ui && bun run test` | pass — 2102 passed, 1 skipped (python); 104 passed (ui) | [`evidence/full-suite.md`](evidence/full-suite.md) |
| T6 | ruff + ruff format + pyright + oxlint + tsc + markdownlint | pass — 0 findings | [`evidence/full-suite.md`](evidence/full-suite.md) |
| T7 | contract review | pass — description updated with PR-endpoint resolution; shapes untouched (parity test in T5 green) | diff of `the-loop.v1.yaml` |
| T8 | demo-fixture render | pass — screenshots committed | [`evidence/`](evidence/) |
| T11 | within T1/T4 | pass — markup renders as text; refusals refuse | [`evidence/full-suite.md`](evidence/full-suite.md) |
| T12 | within T3 | pass — native disclosure elements; labelled textarea/button | [`evidence/full-suite.md`](evidence/full-suite.md) |
| T14 | manual walkthrough | pass — sidebar → tree → stream → chat bar against the fixture (the T8 captures) | [`evidence/`](evidence/) |
