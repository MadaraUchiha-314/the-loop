---
type: evidence
phase: verification
workItem: "issue-300"
status: complete
---

# Verification: nesting work items and their PRs in the sidebar

Executed against `claude/github-issue-300-ab9r0d`, on the same toolchain CI's `ui` job
uses (bun, the lockfile's pinned oxlint 1.78.0, vitest, vite).

## Results

| Row | Type | Result | Evidence |
|-----|------|--------|----------|
| T1 | Unit — `sessionTree` | **pass** | `src/api/model.test.ts`: the two-level tree case updated to the new `SessionNode` shape (`label: "#2"`, `lastActivity: ""`), plus a new case for a PR in another repository (`label: "docs#47"`, `lastActivity` carried from `lastEventAt`); the treeless case unchanged and still green |
| T2 | Component / React | **pass** | `src/App.test.tsx`: `nests each work item's pull requests under it in the sidebar` and `opens the PR's own session from its nested sidebar row`, plus the trace-tab case re-asserted against links |
| T3 | Contract | n/a | no route, request or response shape touched — the diff outside `ui/src` is documentation only |
| T4 | Integration / e2e (service) | n/a | nothing server-side changed |
| T5 | UI / visual | **pass** | Chromium (Playwright) over the production build in demo mode, 1440×900 @2×: [`sidebar-nesting.png`](sidebar-nesting.png) (default view), [`sidebar.png`](sidebar.png) (sidebar with a PR selected), [`pr-selected.png`](pr-selected.png) (the canvas following it) |
| T6 | Accessibility | **pass** | the nested list is queried in the tests by `getByRole("list", { name: "Pull requests for loop-lab#214" })` and the rows by `role="link"`; selection asserted through `aria-current="page"`, not through class names |
| T7 | Regression — deep links | **pass** | the existing `#/item/<unknown>` and pre-283 `#/sessions/<ref>` cases pass unchanged with the trace now route-derived |
| T8 | Lint / typecheck / build | **pass** | `bun run lint` (oxlint --type-aware) clean; `bun run test` 171/171; `bun run build` (`tsc --noEmit` + vite) green |
| T9 | Performance | n/a | one `sessionTree` call per render over the array the sidebar already maps |
| T10 | Migration | n/a | no persisted shape; the hash grammar is unchanged |
| T11 | Security / abuse cases | **pass** | A1: the `viewed` guard in `WorkItemDetail` falls back to the item's own session for a ref the item does not own — exercised by T7's unknown-ref case and read in self-review. A2: the chat bar's `refFor` is the same `viewed` value the panel renders (one value, no second state), and `Transcript.test.tsx`'s "sends the text to the viewed ref" still passes |

## Raw output

```text
$ bun run lint
$ oxlint --type-aware
                                     # no findings

$ bun run test
 Test Files  12 passed (12)
      Tests  171 passed (171)

$ bun run build
$ tsc --noEmit && vite build
dist/index.html                   0.64 kB │ gzip:  0.38 kB
dist/assets/index-CiVSji5W.css   27.49 kB │ gzip:  5.47 kB
dist/assets/index-G572Qq4X.js   279.15 kB │ gzip: 86.63 kB │ map: 1,242.96 kB
✓ built in 1.34s

$ npx markdownlint-cli2@0.18.1 <the docs this PR touches>
Summary: 0 error(s)
```

Test count: **168 → 171** (+1 unit for the foreign-repo label, +2 component for the
nesting and the PR-row selection). No test was weakened: the two edits to existing
assertions are the `sessionTree` shape (two new fields) and the trace tabs having become
links, both of which are the change under test.

## Notes

- The T5 screenshots are captured from `dist/` built with `UI_BASE=/` and served
  statically, with the demo settings seeded into `localStorage` before load — the same
  data the bundled fixture serves the test suite, so the evidence and the assertions
  describe one board.
- The fixture happens to cover every case the requirements name: `loop-lab#214` carries
  a same-repo PR (`#216`) **and** one in another repository (`loop-docs#47`),
  `loop-lab#223` is the ad-hoc (treeless) item, `loop-lab#187` is armed with no session
  at all, and `#207`'s session is closed — so its dot renders grey under a live parent.
