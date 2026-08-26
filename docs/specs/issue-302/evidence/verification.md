---
type: evidence
phase: verification
workItem: "issue-302"
status: complete
---

# Verification: a pull request appears once on the board

> The plan in [`testing-plan.md`](../testing-plan.md), executed. Every row is either a
> result or the reason it does not apply.

## Results

| # | Type | Result | Evidence |
|---|------|--------|----------|
| T1 | Unit — the join | **pass** | `bun run test -- src/api/model.test.ts` — six cases under *a pull request is not a work item of its own*: the linked, labeled PR renders once; an unclaimed PR keeps its row; a treeless owner's claim is refused for all three treeless loops; a PR with a session record of its own keeps its row **and** its own tmux target; a self-claim and a mutual two-level claim leave every row standing |
| T2 | Unit — the fold | **pass** | same file, five cases under *what the removed row carried is folded, not dropped*: the record and the `poll.lastPolledAt` age fallback (through `sessionTree` as well), `recent error · PR` on the owner's card with the PR's short ref, the `needs input` chip plus a single Reply entry that replaces the raw `awaiting-input` row, the human gate **not** promoted to a chip, and nothing folded for a PR that kept a row of its own |
| T3 | Component / React | **pass** | `bun run test -- src/App.test.tsx` — *draws a linked pull request once, under its work item and not beside it*: `#216` is inside `Pull requests for loop-lab#214`, and no top-level `lp-side-row` names `loop-lab#216` |
| T4 | Unit — the service | **pass** | `uv run pytest tests/test_core_attention.py` — an armed PR whose only live session is a nested endpoint reports no `armed-without-session`; a **closed** nested endpoint still does |
| T5 | Contract (OpenAPI) | n/a | no route, request or response shape touched; `docs/api-specs/openapi/` is unchanged, and `GET /work-items` still serves every portable record (R4.1) |
| T6 | Integration / end-to-end | n/a | no routing, dispatch or registry write path changed; the poller and `link_pull_request` are untouched. The full Python suite (T10) covers that nothing moved under them |
| T7 | UI / visual | **pass** | Chromium (Playwright) over the production build in demo mode, 1440×900 @2×, against a fixture that now carries **both** identities for `#216`: [`sidebar-before-duplicate.png`](sidebar-before-duplicate.png) — `loop-lab#216` as a dead top-level row (dash dot, "2m ago") directly above `loop-lab#214`, which already nests `#216`; [`sidebar-one-row-per-pr.png`](sidebar-one-row-per-pr.png) — the same board with one row for the PR, nested, live, "9m ago" |
| T8 | Accessibility | **pass** | the nested list is still `getByRole("list", { name: "Pull requests for loop-lab#214" })`, and the assertion that no top-level row names the PR is read off the rendered links, not the classes alone |
| T9 | Regression | **pass** | the full vitest suite, including every issue-300 case: labels, treeless loops, the trace tabs, `#/item/<ref>` and the pre-283 `#/sessions/<pr-ref>` deep links |
| T10 | Lint / typecheck / build | **pass** | `bun run lint` (oxlint `--type-aware`) clean, `tsc --noEmit` clean, `vite build` green; `uv run ruff check .` clean, `ruff format --check` clean, `uv run pyright the_loop/core/attention.py` 0 errors, `uv run pytest` 2679 passed / 1 skipped; markdownlint clean on every doc touched |
| T11 | Security / abuse case | **pass** | A1 — the self-claim and mutual-claim cases in T1 prove a record cannot walk the join into removing a row; A3 — T4's closed-endpoint case proves a dead endpoint does not suppress a genuine `armed-without-session` |
| T12 | Performance | n/a | one extra pass over the sessions array the join already maps, and one nested loop over the list `list_attention` already walks. No fetch, no hot path |

## Test counts

- **UI: 171 → 183** (+12): six join cases, five fold cases, one component case.
- **Service: 2677 → 2679** (+2): the nested-endpoint liveness case and its closed-endpoint
  counterpart.

No test was weakened, and no existing assertion was edited. Every new test was run against
the unfixed code first: the seven UI cases and the liveness case fail there — including
issue-300's own *"opens the PR's own session from its nested sidebar row"*, which the
fixture's second identity breaks until the join reconciles it.

## Notes

- The demo fixture gained the missing half of the real shape: `makePullRequestRecord(216)`,
  the poll ledger the poller flushes under a labeled PR's own ref. Without it the bundled
  data could not reproduce the defect, and the screens would keep being evaluated against
  a board no service produces.
- The T7 screenshots are captured from `dist/` built with `UI_BASE=/` and served
  statically, with the demo settings seeded into `localStorage` before load — the same
  data the suite asserts against, so the evidence and the assertions describe one board.
  The "before" shot was taken with the claim check disabled at
  `buildWorkItemViews`, nothing else changed.
- `uv.lock` was left untouched: running `uv run` rewrites an unrelated
  `typing-extensions` marker and the `11.5.0 → 11.6.0` version line that `main` already
  carries out of sync. Neither belongs in this diff.
