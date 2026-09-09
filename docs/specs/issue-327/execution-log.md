---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#327"
phase: needs-review
status: in-progress
---

# Execution Log: Control Plane UI 3.0

> Append-only log of progress for the user's visibility.

## Process note

The owner opened [#327](https://github.com/MadaraUchiha-314/the-loop/issues/327) with a
**finished prototype** (https://the-loopy-one.lovable.app/) and a direct instruction:
remove the presentational components, replace them with the prototype, support light and
dark, invent no functionality, and prove it in a browser. As with issue-298 the design
phase arrives locked by the owner — the prototype is the visual contract, explored in a
browser and checked in as stills under [`design/screenshots/`](design/screenshots/). The
change is presentation-only over unchanged connectors, so it is tier 3
(`human-approves-pr`). No authorized `the-loop execute` reaches this cloud session, so
the selection is recorded here and every phase is walked; the spec chain is authored in
full because the rewrite touches every view.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-09 | — | Tier 3. Brainstorming skipped: the prototype is the answer. All other phases walked. |
| requirements-definition | 2026-09-09 | | [`requirements.md`](requirements.md) — six requirements, three abuse cases |
| design | 2026-09-09 | @MadaraUchiha-314 (prototype attached to the issue) | [`design.md`](design.md) — element → data mapping, tokens, theme mechanism; [`decision-112`](../../decisions/decision-112.md) |
| test-planning | 2026-09-09 | | [`testing-plan.md`](testing-plan.md) — thirteen rows, nine applicable |
| tasks-breakdown | 2026-09-09 | | [`tasks.md`](tasks.md) — twelve tasks |
| implementation | 2026-09-09 | | On `claude/github-issue-327-8vubsj` — tasks 1–12 |
| verification | 2026-09-09 | | [`evidence/verification.md`](evidence/verification.md) — rows T1, T2, T5, T8, T9, T10, T12, T13; 26 stills in both themes |
| needs-review | 2026-09-09 | | PR #328 briefing rewritten; awaiting the owner (tier 3: `human-approves-pr`) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#328](https://github.com/MadaraUchiha-314/the-loop/pull/328) | tasks 1–12: the whole work item | open |

## Progress entries

### 2026-09-09 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–12. Tokens and the `.dark` theme as a Tailwind `@theme` in `app.css`
  (Classical deleted); the `theme` setting and `state/theme.ts`; the pre-paint script in
  `index.html`; inline icons; `StatusDot`, `PhaseChip`, `IconButton`, `Section`/`KV`,
  `Notice`, `ControlButton`, `renderInline`; `Sidebar` (groups via `sidebarGroup`, search via
  `filterViews`, nested PR rows, Standing group, footer with the health word); `GraphStrip`
  (`compactRail`, Full graph); `SessionTabs`; the trace and composer in `Transcript.tsx`;
  `SessionAside`; the gate and question banners; `HeaderBar` with the theme toggle and the
  panel reopen controls; `Work` composing the three columns with `Standing` and `Settings`
  as panes; `App` with the banners, the theme effect and the viewport-default panel state.
  `ui/src/api/`, `ui/src/demo/` and every `state/` file but `settings.ts` are untouched.
  Then the verification run and the docs.
- **Checkpoint/tests:** `bun run lint` clean, `bun run test` 212/212, `bun run build`
  green, markdownlint 0 errors — [`evidence/verification.md`](evidence/verification.md).
- **Self-review:** four passes. Pass one, on the rendered screens: graph-strip node labels
  clipped (the `<li>` shrank under its `shrink-0` child — fixed), the sidebar meta line
  crowded four fields into a truncated row (the flag now takes the node's slot), the tmux
  attach command wrapped (truncated). Pass two, on the diff: seven icons drawn but never
  used (removed), the pre-paint script's `matchMedia` unguarded (wrapped), and a 390 px
  viewport where an opened sidebar squeezed the main column to a sliver (the panels overlay
  below `md`). Pass three: the trace file typed props through the global `React` namespace
  where every other file imports `ReactNode` (made consistent); the evidence script tripped
  the app's lint (excluded like `dist`). Pass four: nothing new.
- **Next:** the owner's review on PR #328.
- **Blockers:** none.

### 2026-09-09 — the owner's first review round: fonts, spacing, wrapping

- **Phase:** needs-review
- **Did:** on PR #328 the owner asked that fonts and spacing match the prototype and that
  long text wrap. Measured the built app against the prototype's recorded numbers — panel
  widths, every bar height, chip / node / switch / icon-button sizes, the four font faces
  and weights, the reading measure — all equal; one 3 px header difference from a
  line-height added in the same round, reverted. Long values now wrap instead of
  truncating: the page title, the sidebar row's title (two lines, clamped), every panel
  value, the tmux attach command, the composer hint; the meta line and a collapsed tool
  call's summary stay single-line with the full text in `title`. Evidence extended with
  the measurement table and a synthetic long-text pair
  ([`evidence/verification.md`](evidence/verification.md) § Fonts and dimensions).
- **Checkpoint/tests:** lint clean, 212/212, build green, markdownlint clean.
- **Next:** the owner's review.
- **Blockers:** none.

### 2026-09-09 — prototype explored, spec chain drafted

- **Phase:** phase-selection → tasks-breakdown
- **Did:** captured the prototype in headless Chromium — 79 stills in both themes, the
  rendered DOM of every screen, every design token from its Tailwind build (oklch, `.dark`
  class strategy, fonts, radius, the three custom utilities) and its component code
  (compaction rule, tools switch, session panel sections). Inventoried the current
  dashboard's functionality surface (every action, state, route, setting, test) so the
  rewrite can be checked against it. Wrote the four artifacts and the decision. Added
  Tailwind v4 to the build (commit `ae91ccb`; CI green) and opened PR #328 with an
  in-progress briefing.
- **Checkpoint/tests:** baseline — `bun run test` 183 passed (12 files); `tsc --noEmit`
  clean.
- **Next:** task 1 (tokens, theme setting), red first.
- **Blockers:** none.

## Verification results

> With a `testing-plan.md` the `verification` node records its results there.

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
| — | — | — | see `testing-plan.md` |

## Design critic review

> Not selected for this work item.

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| | | | | |

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self (rendered screens) | the-loop (this session) | new findings — clipped node labels, crowded sidebar meta line, wrapping tmux command: fixed | this log |
| 2 | self (diff) | the-loop (this session) | new findings — unused icons, unguarded `matchMedia`, narrow-viewport squeeze: fixed | this log |
| 3 | self (diff) | the-loop (this session) | new findings — `React.` namespace types, evidence script under the app's lint: fixed | this log |
| 4 | self (diff) | the-loop (this session) | zero (converged) | this log |
| — | critic | — | unavailable — `reviews.critics` is empty in this repository's config; does not count toward `criticReviewCount` | — |
| 5 | security | the-loop checklist | pass — three abuse cases, three closed | [`evidence/verification.md`](evidence/verification.md) § Security |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no security-review
  skill is invocable from this session's plugin set)
- **Outcome:** pass — [`evidence/verification.md`](evidence/verification.md) § Security:
  abuse case 1 (markup / `**` / backtick payloads render as text) by two tests, abuse case
  2 (unknown stored theme ignored) by a test, abuse case 3 (the pre-paint script evaluates
  nothing from storage) by review; no `dangerouslySetInnerHTML`, `innerHTML` or `eval` in
  the app. No new request, route, credential or runtime dependency.
- **Human sign-off:** n/a (tier 3, below `humanSignOffMinTier: 4`)

## Final validation evidence

| Requirement | Proof |
|-------------|-------|
| R1.1 three columns, viewport-locked | `01-home-*.png`, `02-item-214-*.png`; `App.test › collapses the sidebar and the session panel` |
| R1.2–R1.3 tokens, no shadows, the three faces | `app.css` `@theme` (the prototype's oklch values, `design.md` table); every still |
| R1.4 dot + chip state language | `StatusDot`, `PhaseChip`; `grouping.test › itemStatus`; `07-gate-*.png` |
| R1.5 grouped sidebar | `grouping.test › sidebarGroup`; `App.test › lists every tracked work item…grouped`; `01-home-*.png` |
| R1.6 compacted node strip + Full graph | `GraphStrip.test`; `03-full-graph-*.png` |
| R1.7 trace idioms + Tool calls switch | `Transcript.test`; `App.test › hides the tool groups…`; `04-tools-expanded-*.png`, `05-tools-off-*.png`, `06-pr-session-*.png` |
| R2.1–R2.5 theme: preference, toggle, persisted, pre-paint, validated | `theme.test`, `settings.test › the theme setting`, `App.test › switches theme…`; `index.html` script; every `-light` / `-dark` pair |
| R3.1 connectors byte-identical | `git diff 5495800 -- ui/src/api ui/src/demo ui/src/state` touches only `settings.ts` (+ new `theme.ts`) |
| R3.2–R3.3 every action and state has a home | the existing `App.test`, `Standing.test`, `ConfigEditor.test`, `WorkItemDetail.test` scenarios green; `07-gate`, `08-fallback`, `09-standing`, `10-settings` stills |
| R3.4 nothing unbacked; search and copy do exactly that | no *New work item* / checks / cleanup in the tree; `grouping.test › filterViews`; `App.test › filters the sidebar…` |
| R3.5 hashes and anchors unchanged | `route.ts` untouched; `App.test › survives a deep link…`, `› lands a pre-283 sessions deep link…` |
| R4.1–R4.5 reading measure, `role="log"`, `aria-current`, `<details>`, Enter + Space, reduced motion | `WorkItemDetail.test`, `App.test › hides the tool groups…`; `grep prefers-reduced-motion` |
| R4.6 narrow viewports | `12-mobile-*.png`, `12b-mobile-sidebar-*.png` |
| R5 browser evidence, both themes | `evidence/verification.md` § UI / visual, 26 stills; embedded in the PR briefing |
| R6 docs follow | `ui/README.md`, `docs/capabilities/control-plane.md` (below) |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`docs/capabilities/control-plane.md`](../../capabilities/control-plane.md) | the "two surfaces / Classical" behaviour bullet replaced by the one-screen, three-column behaviour: groups, node strip, session tabs, trace switch, session panel, panes, panel collapse and viewport defaults, the design system and its tokens, light/dark with persistence and pre-paint, nothing unbacked rendered | `issue-327` row added above `issue-298` |

## Documentation

| Document | What changed |
|----------|--------------|
| [`ui/README.md`](https://github.com/MadaraUchiha-314/the-loop/blob/main/ui/README.md) | the screen description rewritten for the three columns and the groups; a **Design system** section (the prototype, tokens as a Tailwind theme, decision-112, light and dark); the layout tree for the new components; a **Screenshot evidence** section for `scripts/screenshots.mjs`; the Classical vendored-stylesheet note removed |
| `skills/the-loop/**`, `README.md`, the docs site | unchanged — none of them describes the dashboard's look; the docs site embeds `ui/README.md` |
