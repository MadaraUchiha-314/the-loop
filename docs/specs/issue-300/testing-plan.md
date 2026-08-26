---
type: testing-plan
phase: test-planning
workItem: "issue-300"
status: locked
approvedBy: []
overrides: {}
---

# Testing plan: nesting work items and their PRs in the sidebar

> Derived from the locked `requirements.md` and `design.md`, **before** `tasks.md`.
> Authored at `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `sessionTree`'s two new fields: the number-alone label for a same-repo PR, the qualified label for a PR elsewhere, `lastActivity` carried from the endpoint, and the treeless rule still returning no children | `cd ui && bun run test -- src/api/model.test.ts` |
| T2 | Component / React (behaviour) | yes | the sidebar renders one nested list per item that has PR sessions, named for the item; an item with none renders no list; a nested row opens the PR's session on the owning item's canvas; the owning row keeps its marker without claiming the selection | `cd ui && bun run test -- src/App.test.tsx` |
| T3 | Contract (OpenAPI) | n/a — no route, request or response shape is touched; the change is client-side rendering and hash routing over records the page already reads (R5.1) | | |
| T4 | Integration / end-to-end (service) | n/a — nothing server-side changed; the Python suite's relevance to this diff is only that it must remain untouched, which T8 covers | | |
| T5 | UI / visual | yes | the rendered sidebar in a real browser against the demo fixture: indent, gutter hairline, both label forms, the three row states, and the canvas switching trace when a nested row is clicked. `design.uiArtifacts.screenshotEvidence` requires the screenshots | Chromium via Playwright over the production build, demo mode |
| T6 | Accessibility | yes | the nested list is a real list with an accessible name per item, and the selected row at either level carries `aria-current="page"` — asserted through the roles, not the classes | `cd ui && bun run test -- src/App.test.tsx` (queried by role/name throughout) |
| T7 | Regression — deep links | yes | `#/item/<item-ref>`, `#/sessions/<pr-ref>` (pre-283) and an unknown ref keep their existing behaviour now that the trace is route-derived (R4.4) | `cd ui && bun run test -- src/App.test.tsx` |
| T8 | Lint / typecheck / build | yes | the three commands CI and the Pages publish run, at the versions the lockfile pins | `cd ui && bun run lint && bun run test && bun run build` |
| T9 | Performance / load | n/a — one `sessionTree` call per render over the same array the sidebar already maps, and rows only for endpoints already in memory. No fetch, no hot path | | |
| T10 | Migration / upgrade | n/a — no persisted shape. The hash grammar is unchanged (a PR ref was already a valid `#/item/` and `#/sessions/` ref) | | |
| T11 | Security / abuse case | yes | A1 — a ref the shown item does not own falls back to the item's own session instead of being requested; A2 — the chat bar's target is the same resolved ref the panel renders | A1 by the `viewed` guard, covered by T7's unknown-ref case and read in review; A2 by construction (one value) and `Transcript.test.tsx`'s existing "sends the text to the viewed ref" |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R2.2 | a PR in its work item's repository labels as `#2` |
| T1 | R2.3 | a PR in another repository labels as `docs#47`, and carries its `lastEventAt` |
| T1 | R1.3, R1.4 | the tree stays two levels; an ad-hoc / contribution / review item has `inner: []` even with a linked PR endpoint |
| T2 | R1.1, R1.2, R2.2, R2.3 | "nests each work item's pull requests under it in the sidebar" — two rows under `loop-lab#214`, printed `#216` and `loop-docs#47`; no list for an item without PR sessions |
| T2 | R3.1, R3.2, R3.4 | "opens the PR's own session from its nested sidebar row" — the canvas stays on `Control plane UI over /api/v1`, the `loop-lab#216` tab becomes current, the PR row is `aria-current`, the item row is not but keeps `owner` |
| T2 | R4.2, R3.3 | the trace tabs are links to the same `#/item/<ref>` hash the sidebar rows use |
| T5 | R1.1, R1.5, R2.1, R2.4, R3.4 | the rendered sidebar: nested rows are dot + label + age only, the item rows keep dot/ref/age/title/chip, the parent tint marks the open item |
| T6 | R1.1 | `getByRole("list", { name: "Pull requests for loop-lab#214" })` — the nesting is in the accessibility tree |
| T7 | R4.4 | the pre-283 `#/sessions/<pr-ref>` deep link still lands on the owning item; an unknown ref still says so |
| T8 | R5.1, R5.2 | nothing outside `ui/src` changed; the app lints, types, tests and builds |

## Verification results

Recorded at `verification` in [`evidence/verification.md`](evidence/verification.md),
with the T5 screenshots beside it.
