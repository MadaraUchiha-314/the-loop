---
type: testing-plan
phase: test-planning
workItem: "issue-327"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: Control Plane UI 3.0

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md), before
> `tasks.md`. Authored at `test-planning`, completed at `verification`.
>
> **This file is executable content.** Credentials appear by reference only — none are
> needed here.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | view-side helpers: `sidebarGroup`, `compactRail`, theme resolve/persist, search filter, `renderInline`; the existing model/state/client suites stay green untouched | `cd ui && bun run test` |
| T2 | Integration (scenario) | yes | the React suite on the demo transport (`App.test.tsx`, `Standing.test.tsx`, `WorkItemDetail.test.tsx`, `Transcript.test.tsx`, `ConfigEditor.test.tsx`): every action and state of R3 still reachable through the new surface; new cases for the theme toggle, the tools switch, the Full graph toggle and the panel toggles | `cd ui && bun run test` |
| T3 | Contract (OpenAPI) | n/a — no route, request or response shape changes; `ui/src/api/` is byte-identical | | |
| T4 | End-to-end | n/a — no live service in this environment; the demo transport is the same client interface over the same record shapes | | |
| T5 | UI / visual | yes | the built app, demo mode, headless Chromium at 1440×900 and 390×844, **both themes**: home, PR session, full graph, tool calls off, gate + question banners, Standing, Settings, panels collapsed | `node ui/scripts/screenshots.mjs` (checked in under `docs/specs/issue-327/evidence/`) |
| T6 | Snapshot | n/a — DOM snapshots would freeze the very markup this item rewrites; the visual pass (T5) and the role/label suite (T2) are the assertion | | |
| T7 | Performance / load | n/a — no data path changes; the bundle size is recorded in the build evidence for the reviewer | | |
| T8 | Security / abuse case | yes | AC1: markup and `**`/backtick payloads in transcript text render as text and create no element; AC2: an unknown stored theme is dropped; AC3: grep for `dangerouslySetInnerHTML` / `innerHTML` / `eval` is empty | `bun run test`; `grep -rn "dangerouslySetInnerHTML\|innerHTML\|eval(" ui/src ui/index.html` |
| T9 | Accessibility | yes | `role="log"` + name + focus on the trace; `aria-current` on rows, tabs and nodes; the tools switch toggles on Enter and Space; disclosures are `<details>`; `prefers-reduced-motion` guard present in the stylesheet | `bun run test`; `grep -n "prefers-reduced-motion" ui/src/styles/app.css` |
| T10 | Migration / upgrade | yes | a stored `the-loop:settings:v1` without `theme` loads with theme unset and follows the browser preference; every other key round-trips as before | `bun run test` (`settings.test.ts`) |
| T11 | Manual exploratory | n/a — no live workstation service here; the demo transport exercises every verb, and the owner's PR review is the human pass | | |
| T12 | Lint / typecheck / build | yes | the same three commands CI and the Pages publish run | `cd ui && bun run lint && bun run build` (build runs `tsc --noEmit` first) |
| T13 | Markdown lint | yes | the spec, decision and docs pass the repository linter | `npx --yes markdownlint-cli2@0.18.1 "**/*.md"` from the repo root |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.5 | `sidebarGroup` puts a parked/questioned/blocked item in needs-you, an active one in in-flight, an all-done one in shipped, the rest in idle |
| T1 | R1.6 | `compactRail` keeps first, last and ±2 around the current node, one gap between |
| T1 | R2.1, R2.5 | theme resolves to the browser preference when unset or invalid |
| T1 | R3.4 | the search filter matches ref, title, repo and node, case-insensitively |
| T1, T8 | Sec AC1 | `renderInline` returns strings inside `<strong>`/`<code>`; a payload with `<img>` creates no element |
| T2 | R3.2, R3.3, R3.5 | every existing `App.test.tsx` scenario, re-pointed where it selected Classical classes |
| T2 | R2.2 | clicking the theme control flips the `dark` class and persists the choice |
| T2 | R1.7, R4.4 | the tools switch hides tool groups; Enter and Space toggle it |
| T2 | R1.6 | Full graph shows every node; Collapse graph compacts again |
| T2 | R4.6 | collapsing the sidebar shows the open-sidebar control in the header |
| T5 | R1, R2, R4.1, R5 | the screenshot set in both themes |
| T9 | R4.2, R4.3 | existing `WorkItemDetail.test.tsx` and `App.test.tsx` role assertions |
| T10 | R2.5, Sec AC2 | settings migration and unknown theme value |
| T12, T13 | NFR | lint, types, build, markdown |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none — demo mode, no network beyond the fonts request the
  screenshot script blocks so captures are deterministic.
- **Fixtures & data:** `ui/src/demo/fixture.ts`, unchanged.
- **Credentials:** none.
- **Bring-up:** `cd ui && bun install --frozen-lockfile && bun run build && bun run preview`
  (or the script's own static server over `dist/`). **Tear-down:** stop the server.
- **If bring-up fails:** record it under Verification results, leave T5 unticked, escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T9, T10 | vitest summary (files, tests, duration) | `verification.md` § Tests |
| T12 | lint output; `tsc` + vite build output with bundle sizes | `verification.md` § Lint · § Build |
| T13 | markdownlint output | `verification.md` § Markdown |
| T5 | one PNG per screen per theme, indexed with the prototype still each matches | `*.png`, table in `verification.md` § UI / visual |
| T8 | the grep output | `verification.md` § Security |

## Verification activities

- [ ] T1/T2/T8/T9/T10 — `cd ui && bun run test`
- [ ] T12 — `cd ui && bun run lint && bun run build`
- [ ] T13 — `npx --yes markdownlint-cli2@0.18.1 "**/*.md"`
- [ ] T8 — `grep -rn "dangerouslySetInnerHTML\|innerHTML\|eval(" ui/src ui/index.html` (expect no matches)
- [ ] T9 — `grep -n "prefers-reduced-motion" ui/src/styles/app.css` (expect a match)
- [ ] T5 — `node ui/scripts/screenshots.mjs` against the built bundle; copy the captures into `evidence/`

## Verification results

_Not yet executed._

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |

**Not executed:** —

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed.
