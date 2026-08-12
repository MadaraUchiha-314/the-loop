---
type: execution-log
workItem: issue-207
phase: implementation
status: in-progress
---

# Execution Log: a control-plane dashboard over `/api/v1`

> Append-only log for issue-207. Ticket:
> [#207](https://github.com/MadaraUchiha-314/the-loop/issues/207) — **provisional, see
> below**.

## Provenance and what is unreconciled

This chain was authored from a Claude Design handoff bundle (`Control Plane.dc.html`, one
transcript) implementing the design the owner iterated on there. The authoring session ran
in a container with **no GitHub write credential**: `git clone` over the proxy works
anonymously, `git push` and the GitHub API do not.

Three consequences, all for a human to close:

1. **No ticket was filed.** `206` was taken as the next free number. Reconciling means
   filing the issue, then `git mv docs/specs/issue-207 docs/specs/issue-<real>` and
   updating the front-matter `workItem` and the three ticket links in this directory.
   → **Closed.** The owner filed the work as
   [#207](https://github.com/MadaraUchiha-314/the-loop/issues/207) and carried the branch
   in; `206` had meanwhile been taken by an unrelated PR. This directory was renamed and
   its `workItem` front-matter and ticket links repointed at `207`.
2. **No `loop:<phase>` label was applied**, because there is no ticket to apply it to.
   → **Closed.** `loop:in-review` applied to #207 on hand-off to the PR.
3. **The spec chain was authored alongside the implementation, not before it.** The
   CLAUDE.md rule is spec-then-code; this session had one pass and no gate to wait on, so
   the artifacts are honest descriptions of what was built rather than approvals that
   preceded it. Reviewers should read them as a proposal to ratify, not as a locked chain.

Two design questions were also left at their recommended defaults because the session
could not get an answer: scope stops at the UI (the two proposed backend verbs are
follow-ups), and the deployed page offers a demo fixture rather than a cold connection
error.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-12 | — | Not run: no ticket, so no checklist was posted and none was waited on. Phases assumed: the full spec chain, verification, review. `brainstorming` and `design-critic-review` (opt-in) not selected — the design phase happened in Claude Design, and its transcript is the brainstorm record |
| requirements-definition | 2026-08-12 | | [`requirements.md`](requirements.md) drafted — five requirements, four NFRs, five abuse cases. Risk tier **4**: `autonomy.inferFromChange` matches `sensitivePaths: .github/workflows/**` (the Pages workflow is rewritten), so the gate is `human-approves-pr` and a **named human security sign-off** is required (`security.review.humanSignOffMinTier: 4`) |
| design | 2026-08-12 | | [`design.md`](design.md) drafted — one transport interface with two implementations, one pure join module, a two-round board hook |
| test-planning | 2026-08-12 | | [`testing-plan.md`](testing-plan.md) drafted — 8 rows in scope, 3 `n/a`/manual with reasons, and an explicit § Coverage gaps |
| tasks-breakdown | 2026-08-12 | | [`tasks.md`](tasks.md) drafted — 12 tasks, two independent roots after the scaffold |
| implementation | 2026-08-12 | | Built. 44 tests pass; `bun run lint` (type-aware) and `tsc --noEmit` clean; the production bundle builds with the Pages base path |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| `feat/control-plane-ui` | the whole work item | **local branch, unpushed** — no write credential in the authoring container |

## Progress entries

### 2026-08-12 — the dashboard

Read the handoff bundle and the transcript, then the API surface the design claims to sit
on: `the_loop/api/app.py`, the core modules behind it, `docs/cli/state.md` for the record
shapes and both shipped graph YAMLs for the node ids.

Three things the research changed about the design as drawn:

- **Loop position is a two-round fetch, not a column.** `graph/check` needs a checkout
  path that only the session record has and a spec id that only the portable record has,
  so the board paints the flat lists first and the positions as they arrive. An item with
  no session on this machine keeps its row and shows its frozen node list.
- **Two of the prototype's surfaces have no route behind them.** The prototype's seed data
  made the inline reply box and the turns-and-tool-calls trace look shipped; neither
  exists. They are built and rendered disabled, naming the route that would enable them,
  rather than dropped or mocked.
- **Ticket titles and PR checks are not the-loop's to serve.** The portable record keeps a
  `ref` and a `url`, deliberately not a copy of GitHub's mutable fields. The board links
  out; only the demo fixture carries titles.

The node ids in the demo fixture were taken from `pdlc-work-item-loop.yaml` and
`pdlc-pr-loop.yaml` rather than the prototype's shorthand, so what the demo teaches
transfers to a real board.

Deployment: Pages serves one artifact per origin, so a second workflow would replace the
docs deploy rather than sit beside it. `docs.yml` now builds both and copies `ui/dist`
into the VitePress output under `ui/`.

## Verification results

| Row | Result | Evidence |
|-----|--------|----------|
| T1 | pass — 22 tests | `bun run test src/api/model.test.ts` |
| T2 | pass — 7 tests | `bun run test src/api/client.test.ts` |
| T4, T9 | pass — 8 tests, selectors are role + accessible name only | `bun run test src/App.test.tsx` |
| T8 | pass — 7 tests | `bun run test src/state/settings.test.ts` |
| T8b | pass — no `dangerouslySetInnerHTML`, `eval`, `new Function` or `innerHTML` in `ui/src` | grep |
| T10 | pass — new store, versioned from birth; absent store is the default path | T1/T8 |
| T5, T7, T11 | **not executed** | T5 and T11 need a human at a browser; T7 is a review item. T11 in particular has never been run against a real service — see below |

**The gap that matters.** Nothing in this pass has talked to a running `the-loop service
start`. The transport is pinned against the authored OpenAPI contract and the record
shapes in `docs/cli/state.md`, and the demo fixture is built to those same shapes — but a
fixture cannot discover that a field is spelled differently in practice. T11 is the first
thing to run before this merges.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (this session) | new findings — the first cut of `sessionState` narrowed a `(string & {})` union by comparison and let an unknown status through as itself; and `parseRef` accepted `github:/owner/repo#1` because a three-segment split with an empty host still produced an owner and a repo. Both closed, both covered by T1 | [`model.ts`](../../../ui/src/api/model.ts) |
| 2 | self | the-loop (this session) | new findings — the behavioural suite asserted on the first paint and so raced the graph round; rewritten to re-read the row inside `waitFor`, which is also what documents the two-round contract | [`App.test.tsx`](../../../ui/src/App.test.tsx) |
| 3 | security | — | **not run.** Risk tier 4 requires a named human sign-off; no reviewer was available to this session | |
