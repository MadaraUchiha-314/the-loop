---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#511"
status: approved
approvedBy: ["MadaraUchiha-314"]
overrides: {}
---

<!-- Written per the `the-loop:writing` skill. -->

# Testing plan: de-cluttering the control plane UI (Option C — Minimal)

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md) — the
> **C** columns of its component table and element inventory — before `tasks.md`.
> Authored at `test-planning`, completed at `verification`.
>
> **This file is executable content.** It names commands an agent will run. Credentials
> appear by reference only — none are needed here.

## Test matrix

The proof is three-fold: the component suites assert each inventory verdict and every
preserved action and state; headless screenshots of the **built** app prove the rendering
against the locked prototype in both themes; the CI commands and a bundle comparison prove
the non-functional requirements. Everything runs on the demo fixture — no service, no
credential.

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `railNote` no longer names the node; `sidebarGroup` still answers four ways while the sidebar maps to **Needs you** / **Everything else** sorted by last activity (`SIDEBAR_GROUPS_MINIMAL`); `compactRail` and `railLabel` unchanged; `filterViews` unchanged; `rowFlag` unchanged; `chatBlocked` unchanged | `cd ui && bun run test` |
| T2 | Integration (scenario) | yes | the React suites on the demo transport (`App.test.tsx`, `Sidebar.test.tsx`, `GraphStrip.test.tsx`, `WorkItemDetail.test.tsx`, `Transcript.test.tsx`, a new `SessionFacts.test.tsx`): every inventory verdict for C — what each band renders by default and what a disclosure reveals; every action of issue-327's functionality map still reachable (R5.2); every state still rendered (R5.3); the one-session tab rule; the single statement of the current node | `cd ui && bun run test` |
| T3 | Contract (OpenAPI) | n/a — no route, request or response shape changes; `ui/src/api/`, `ui/src/state/` and `ui/src/demo/` are byte-identical (R5.1), asserted by T12's diff check | | |
| T4 | End-to-end | n/a — no live service in this environment; the demo transport is the same client interface over the same record shapes, and nothing in the data path changes | | |
| T5 | UI / visual | yes | the built app, demo mode, headless Chromium at 1440×900 and 390×844, **both themes**: Work with #214 selected; PR #216 session (the `work item` kicker beside the verbs); Full graph on; the gate banner (#205); the question banner (#214); Session details open and closed; the search icon open; the no-transcript fallback and blocked composer (#187); Standing; Settings; the sidebar collapsed; 390 px with the sidebar closed and with Session details open — each matched to the prototype still it corresponds to (R7.1) | `node ui/scripts/screenshots.mjs` (extended for the new states), captures copied under `evidence/` |
| T6 | Snapshot | n/a — DOM snapshots would freeze the markup this item removes and relocates; the role/name suite (T2) and the visual pass (T5) are the assertion | | |
| T7 | Performance / load | n/a as a test — no data path changes; the **bundle size** is compared against 20.5.1 as the NFR check in T12 (removal must not grow it) | | |
| T8 | Security / abuse case | yes | AC1: a fixture title `<b>x</b>`, a node name `**n**` and a transcript line with backticks render as text — no element created — through the one-line row, the row's `aria-label`, the header, the Session details popover and the trace; AC2: the popover's rows render from the typed `SessionRecord` / `PullRequestView` fields (the test passes a record whose fields carry markup and asserts `textContent`); fail-closed: the demo banner, the connection banner (`role="alert"`), the `degraded` health word, and the blocked composer's reason all render in the C layout; a grep for HTML-injecting calls is empty | `cd ui && bun run test`; `grep -rn "dangerouslySetInnerHTML\|innerHTML\|eval(" ui/src ui/index.html` |
| T9 | Accessibility | yes | the search toggle and *Full graph* carry `aria-expanded`; Session details is a `<details>` whose summary is named; a sidebar row's accessible name carries `#n`, the title and the flag; `aria-current` on the selected row, tab and node; the trace keeps `role="log"`, its name and `tabindex`; the verbose switch answers Enter and Space; the `prefers-reduced-motion` guard is present; panels start closed below 1280 px (popover always) and 768 px (sidebar) and reopen from the header | `cd ui && bun run test`; `grep -n "prefers-reduced-motion" ui/src/styles/app.css` |
| T10 | Migration / upgrade | n/a — no stored shape changes: the settings key, the theme pre-paint script and the hash grammar are untouched (R4.3, R5.4); T2 asserts every 20.5.1 hash lands on the same surface | | |
| T11 | Manual exploratory | n/a — no live workstation service here; the demo transport exercises every verb, and the owner's review of the implementation PR, with T5's stills beside the chosen prototype's, is the human pass | | |
| T12 | Lint / typecheck / build / bundle / untouched dirs | yes | the same three CI commands; the production bundle's JS and CSS sizes compared with the sizes at the branch point (JS 341 685 B, CSS 24 469 B — `bun run build` on 20.5.1); `git diff --stat <base> -- ui/src/api ui/src/state ui/src/demo` is empty | `cd ui && bun run lint && bun run build`; `ls -l ui/dist/assets`; `git diff --stat origin/main -- ui/src/api ui/src/state ui/src/demo` |
| T13 | Markdown lint | yes | the spec chain, the decision record, `ui/README.md` and `docs/capabilities/control-plane.md` pass the repository linter | `npx --yes markdownlint-cli2@0.18.1 "**/*.md"` from the repo root |
| T14 | Documentation parity | yes | `ui/README.md` § *Where the screens get their data* and `docs/capabilities/control-plane.md` describe the C layout — what each band shows by default and what sits behind a disclosure — and no longer describe the session panel column or the graph strip band as current (R8) | review of the two files against the inventory; recorded in `evidence/documentation.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R2.1, R2.5 | `railNote` returns `parked — awaiting a human` for a parked item and the attention detail otherwise; never the node name |
| T1 | R3.3 | the sidebar's two-group mapping puts needs-you items first and everything else by last activity; `sidebarGroup` still returns the four-way answer for `itemStatus` |
| T2 | R2.2, R3.2, R6.2 | `Scenario: a sidebar row is one line carrying the number, the title and the urgent flag, and its accessible name carries all three` |
| T2 | R2.2 | `Scenario: a paused, merged or closed item shows no flag on its row` |
| T2 | R3.2 | `Scenario: pull request rows nest only under the selected item` |
| T2 | R2.4 | `Scenario: only the Needs you group shows a count` |
| T2 | R3.3 | `Scenario: the Standing group does not render in the sidebar and the Standing surface still lists every standing session` |
| T2 | R3.3, R6.1 | `Scenario: the search box and the instance filter appear behind the search toggle, which carries aria-expanded` |
| T2 | R2.6 | `Scenario: an instance filter renders on a fleet and not on a worker` |
| T2 | R2.1, R3.2 | `Scenario: the header meta is the ref chip, the phase chip, the note and the age — the repository line and the instance chip are gone` |
| T2 | R2.1, R2.5 | `Scenario: the current node is written once — the phase chip — and the gate banner says Human gate without the node` |
| T2 | R3.3, R6.1 | `Scenario: Full graph in the header meta reveals the node row and Collapse graph hides it` |
| T2 | R2.6, R3.3 | `Scenario: the session tab bar renders only when the item has more than one session` |
| T2 | R2.4 | `Scenario: the tab bar carries no session tally and the composer carries no delivery hint` |
| T2 | R3.3, R3.4 | `Scenario: pause, resume, stop and start render in the header and call controlSession with the work item's ref` |
| T2 | R5.2 | `Scenario: with a PR session selected the verbs carry a visible work item label and still target the work item` |
| T2 | R3.3, R2.3, R6.1 | `Scenario: Session details is a closed details element whose body shows harness, status, started, session id, transcript path, cwd, the attach command and Open on GitHub in full` |
| T2 | R5.2 | `Scenario: copy ref and copy attach command write the clipboard` |
| T2 | R5.3 | `Scenario: loading, empty board, missing deep link, no-transcript fallback, truncated tail and blocked composer render their sentences in the C layout` |
| T2 | R5.4 | `Scenario: every hash the 20.5.1 app parses lands on the same surface` |
| T2 | R6.3 | `Scenario: below 768 px the sidebar starts closed and reopens from the header` |
| T5 | R1.1, R4, R7.1 | the screenshot set in both themes, each still beside its prototype counterpart |
| T8 | Sec AC1, AC2 | the markup-bearing fixture through every relocated position; the popover from the typed record |
| T8 | Sec fail-closed | the four warning signals present in the C layout |
| T9 | R6.1, R6.2, R6.4 | roles, names, `aria-expanded`, `aria-current`, `role="log"`, reduced motion |
| T12 | NFR, R5.1 | lint, types, build, bundle not larger, the three directories untouched |
| T13, T14 | R8, NFR | markdown lint; the two documents describe the C layout |

## Verification environment

- **Repositories:** this repo only, branch `issue-511-declutter-control-plane`.
- **Services / containers:** none — demo mode. The screenshot script blocks nothing but
  needs no network; the Google Fonts request may fail offline, and the captures then
  render in system faces, which the evidence notes.
- **Fixtures & data:** `ui/src/demo/fixture.ts`, unchanged (R5.1).
- **Browser:** Chromium from Playwright's install (`PLAYWRIGHT_BROWSERS_PATH`) or
  `CHROMIUM_PATH`; Playwright itself is installed without saving
  (`npm i --no-save playwright`), as `ui/scripts/screenshots.mjs` documents — it is not a
  dependency of the app (NFR: no new dependency).
- **Credentials:** none.
- **Bring-up:** `cd ui && bun install --frozen-lockfile && bun run build && bun run preview --port 4173`.
  **Tear-down:** stop the preview server.
- **If bring-up fails:** record it under Verification results, leave T5 unticked, escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T9 | vitest summary (files, tests, duration) and the list of new or changed test names | `unit.md` (T1), `integration.md` (T2, T9), `security.md` (T8) |
| T12 | lint output; `tsc` + vite build output; the bundle sizes beside 20.5.1's; the empty diff of the three directories | `lint-and-typecheck.md`, `build.md` |
| T13 | markdownlint output | `lint-and-typecheck.md` § Markdown |
| T5 | one PNG per state per theme, indexed with the prototype still each matches; the before/after element count for the briefing (R7.2) | `ui/*.png`, table in `ui-visual.md` |
| T14 | the two documents' sections quoted against the inventory | `documentation.md` |

No flow needs an animated capture: every behaviour verified is a state (open/closed,
on/off, selected) and a pair of stills shows it.

## Verification activities

- [x] T1/T2/T8/T9 — `cd ui && bun run test`
- [x] T12 — `cd ui && bun run lint && bun run build`, then `ls -l ui/dist/assets` against the 20.5.1 sizes
- [x] T12 — `git diff --stat origin/main -- ui/src/api ui/src/state ui/src/demo` (expect empty)
- [x] T13 — `npx --yes markdownlint-cli2@0.18.1 "**/*.md"`
- [x] T8 — `grep -rn "dangerouslySetInnerHTML\|innerHTML\|eval(" ui/src ui/index.html` (expect no matches)
- [x] T9 — `grep -n "prefers-reduced-motion" ui/src/styles/app.css` (expect a match)
- [x] T5 — `node ui/scripts/screenshots.mjs <out-dir>` against `bun run preview` over `dist/`, both themes, 1440×900 and 390×844; copy the captures under `evidence/ui/`
- [x] T14 — read `ui/README.md` and `docs/capabilities/control-plane.md` against the inventory's C column; record in `evidence/documentation.md`

## Verification results

Executed on 2026-10-20 on branch `issue-511-declutter-control-plane` at the head of the
implementation commits, in demo mode, no credentials. Every planned activity ran and
passed; the n/a rows stayed n/a as planned.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 unit | `cd ui && bun run test` | pass — 22 files, 366 tests | [`evidence/unit.md`](evidence/unit.md) |
| T2 integration · T9 accessibility | `cd ui && bun run test` (with `NODE_OPTIONS=--no-experimental-webstorage` on this Node 26 workstation; not needed on CI's Node 22) | pass — every scenario title of the trace table has a test | [`evidence/integration.md`](evidence/integration.md) |
| T8 security / abuse case | `cd ui && bun run test`; `grep -rn "dangerouslySetInnerHTML\|innerHTML\|eval(" ui/src ui/index.html` | pass — abuse cases 1 and 2 and the four fail-closed signals; the grep has no match | [`evidence/security.md`](evidence/security.md) |
| T9 reduced motion | `grep -n "prefers-reduced-motion" ui/src/styles/app.css` | pass — one match, the guard unchanged | [`evidence/integration.md`](evidence/integration.md) |
| T12 lint · typecheck · build | `cd ui && bun run lint && bun run build` | pass — oxlint clean; `tsc --noEmit` clean; built in 1.29 s | [`evidence/lint-and-typecheck.md`](evidence/lint-and-typecheck.md), [`evidence/build.md`](evidence/build.md) |
| T12 bundle | `ls -l ui/dist/assets` against the branch point | pass — JS 337 157 B (was 341 685), CSS 24 421 B (was 24 469) | [`evidence/build.md`](evidence/build.md) |
| T12 untouched directories | `git diff --stat origin/main -- ui/src/api ui/src/state ui/src/demo` | pass — empty | [`evidence/build.md`](evidence/build.md) |
| T13 markdown lint | `npx --yes markdownlint-cli2@0.18.1 "**/*.md"` | pass — 1764 files, 0 errors | [`evidence/lint-and-typecheck.md`](evidence/lint-and-typecheck.md) |
| T5 UI / visual | `node ui/scripts/screenshots.mjs <out> http://localhost:4173/the-loop/ui/` over `bun run preview --port 4173` | pass — 32 stills, both themes, 1440×900 and 390×844, no page error; before/after 56 → 27 | [`evidence/ui-visual.md`](evidence/ui-visual.md), [`evidence/ui/`](evidence/ui/) |
| T14 documentation parity | `ui/README.md` and `docs/capabilities/control-plane.md` read against the inventory's C column | pass | [`evidence/documentation.md`](evidence/documentation.md) |

**Not executed:** T3, T4, T6, T7, T10, T11 — n/a as planned (no contract, data-path,
snapshot, performance, migration or live-service change; the bundle check stands in for
T7 and the owner's PR review, with the stills beside the prototype's, for T11).

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.

### 2026-10-20 — approved

**@MadaraUchiha-314** wrote:

approved
