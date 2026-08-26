---
type: testing-plan
phase: test-planning
workItem: "issue-302"
status: locked
approvedBy: []
overrides: {}
---

# Testing plan: a pull request appears once on the board

> Derived from the locked `requirements.md` and `design.md`, **before** `tasks.md`.
> Authored at `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit — the join | yes | a claimed PR with its own portable record yields **one** view, not two; an unclaimed PR keeps its top-level row; a treeless owner's claim and a claim on a ref with its own session are not honoured; a self-claim and a two-level claim leave every row standing | `cd ui && bun run test -- src/api/model.test.ts` |
| T2 | Unit — the fold | yes | the nested row carries the PR's record and falls back to `poll.lastPolledAt` for its age; the PR's attention and open question reach the inbox on the owner's card, named for the PR; the owner's row raises `needs input`; no other chip is promoted | `cd ui && bun run test -- src/api/model.test.ts` |
| T3 | Component / React | yes | the sidebar draws the PR once — one nested row, no top-level row for the same ref — against a fixture holding both identities | `cd ui && bun run test -- src/App.test.tsx` |
| T4 | Unit — the service | yes | `list_attention` reports no `armed-without-session` for an armed ref whose live session is a nested PR endpoint, and still reports one when that endpoint is closed | `cd cli && uv run pytest tests/test_core_attention.py` |
| T5 | Contract (OpenAPI) | n/a — no route, request or response shape is touched (R4.1); `GET /work-items` keeps serving every record and `GET /attention` keeps its item shape | | |
| T6 | Integration / end-to-end | n/a — no routing, dispatch or registry write path changes; the poller and `link_pull_request` are untouched | | |
| T7 | UI / visual | yes | the rendered sidebar against a demo fixture carrying both identities: one row for the PR, nested, with an age. `design.uiArtifacts.screenshotEvidence` requires the screenshot for a UI change | Chromium via Playwright over the production build, demo mode |
| T8 | Accessibility | yes | the nested list keeps its accessible name and the row count drops by one — asserted through roles, not classes | `cd ui && bun run test -- src/App.test.tsx` |
| T9 | Regression | yes | issue-300's nesting behaviour is unchanged for every item that had no duplicate: labels, treeless loops, deep links, the trace tabs | `cd ui && bun run test` (full suite) |
| T10 | Lint / typecheck / build | yes | the commands CI runs, at the versions the lockfiles pin, on both sides | `cd ui && bun run lint && bun run build`; `cd cli && uv run ruff check . && uv run pytest` |
| T11 | Security / abuse case | yes | A1 — a session claiming another work item, and a two-level claim, cannot remove a row (both covered by T1's hostile-record cases); A3 — a **closed** nested endpoint does not suppress `armed-without-session` (T4) | T1, T4 |
| T12 | Performance | n/a — one extra pass over the sessions array the join already maps, no fetch; the service adds one nested loop over the same list it already walks | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1 | a labeled PR with a portable record **and** an endpoint under its issue renders once |
| T1 | R1.2 | a PR no session claims (linked to no issue) keeps its top-level row |
| T1 | R1.3 | an ad-hoc / contribution / review owner draws no nested rows, so its claimed PR stays top-level |
| T1 | R1.4 | a PR with a session record of its own keeps its row, and keeps reaching its own tmux target |
| T1 | R1.5, A1 | a session listing itself, and a claim by a ref that is itself claimed, leave both rows |
| T2 | R2.1 | the nested row's age falls back to the PR record's `poll.lastPolledAt` |
| T2 | R2.2 | a `recent-error` on the PR's ref appears on the owner's card as `recent error · PR`, with the PR's short ref |
| T2 | R2.3 | an open question on the PR's ref gives the owner a `needs input` chip and a Reply entry keyed to the PR |
| T2 | R2.4 | a PR's human gate does not become a chip on the owner's row |
| T2 | R2.5 | a treeless owner's PR keeps its own row and its own card; the owner reports nothing |
| T3, T8 | R1.1 | the sidebar shows one row for the PR, inside its item's list |
| T4 | R3.1 | an armed ref whose only live session is a nested endpoint is not "armed without a session" |
| T4 | R3.2, A3 | a closed nested endpoint still reports it; nothing else in the attention list changes |
| T7 | R1.1, R2.1 | the rendered board: one row, nested, with an age |
| T9, T10 | R4.1, R4.2 | the rest of the suite is unchanged; both sides lint, type, test and build |

## Verification results

Recorded at `verification` in [`evidence/verification.md`](evidence/verification.md),
with the T7 screenshot beside it.
