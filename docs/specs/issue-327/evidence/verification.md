# issue-327 — verification evidence

The change is presentation-only, so the proof is: the behaviour suite still passes through
the new surface (re-pointed where it selected Classical class names, extended for what the
design adds), the same three commands CI and the Pages publish run come back clean, the
markdown passes the repository linter, the security greps are empty, and the rendered
screens match the prototype in both themes. Captured 2026-09-09 on
`claude/github-issue-327-8vubsj`; the testing-plan rows are named in each heading.

## T12 — Lint (oxlint, type-aware)

```text
$ bun run lint
$ oxlint --type-aware
lint exit 0
```

## T1 / T2 / T8 / T9 / T10 — Tests (vitest — unit + React, demo transport)

```text
$ bun run test
 ✓ src/components/ConfigEditor.test.tsx (13 tests) 638ms
 ✓ src/components/Transcript.test.tsx (8 tests) 412ms
 ✓ src/views/WorkItemDetail.test.tsx (5 tests) 158ms
 ✓ src/views/Standing.test.tsx (8 tests) 3160ms
 ✓ src/components/GraphStrip.test.tsx (6 tests) 137ms
 ✓ src/state/useStream.test.ts (12 tests) 48ms
 ✓ src/components/primitives.test.tsx (3 tests) 41ms
 ✓ src/api/model.test.ts (60 tests) 28ms
 ✓ src/api/client.test.ts (13 tests) 22ms
 ✓ src/App.test.tsx (16 tests) 5284ms
 ✓ src/api/configModel.test.ts (23 tests) 9ms
 ✓ src/state/settings.test.ts (16 tests) 8ms
 ✓ src/state/useControlPlane.test.ts (7 tests) 7ms
 ✓ src/state/theme.test.ts (4 tests) 6ms
 ✓ src/state/stream.test.ts (10 tests) 6ms
 ✓ src/views/grouping.test.ts (8 tests) 6ms
 Test Files  16 passed (16)
      Tests  212 passed (212)
   Duration  8.00s (transform 592ms, setup 1.41s, collect 1.86s, tests 9.97s, environment 5.84s, prepare 1.11s)
test exit 0
```

Four files are new — `state/theme.test.ts` (resolve / apply), `views/grouping.test.ts`
(sidebar groups, dot status, the search filter), `components/GraphStrip.test.tsx`
(compaction, `Full graph`, the empty rail) and `components/primitives.test.tsx` (the inline
renderer, including the attacker-shaped payloads of abuse case 1) — and `settings.test.ts`
gains the theme key's round-trip, absence and unknown-value cases (T10, abuse case 2).
`App.test.tsx` gains the tools switch (mouse, Enter, Space — T9), the theme toggle and its
persistence, the panel collapse/reopen, and the search filter. Every pre-existing
behavioural assertion — sidebar rows and nesting, the parked chip and in-place gate
approval, the question banner closed by the composer's reply, the transcript-backed trace,
the deep links, the standing-session verbs and refusals, the config editor — is unchanged
and green; the only edits to existing tests replace `.lp-*` class selectors with `data-*`
hooks and the retired "Work items" heading with the design's group headers.

## T12 — Build (`tsc --noEmit`, then the production bundle)

```text
$ bun run build
$ tsc --noEmit && vite build
vite v7.3.6 building client environment for production...
transforming...
✓ 59 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   1.98 kB │ gzip:  0.93 kB
dist/assets/index-B1yFHilJ.css   20.56 kB │ gzip:  5.08 kB
dist/assets/index-BjRgQNZH.js   310.09 kB │ gzip: 95.42 kB │ map: 1,334.67 kB
✓ built in 1.29s
build exit 0
```

The generated stylesheet is 20.6 kB (5.1 kB gzipped), against 30.7 kB for the Classical
pair it replaces; the JS bundle grows by ~20 kB (inline icons, the three new components).

## T13 — Markdown

```text
$ npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/** !docs/specs/*/design/**
Linting: 991 file(s)
Summary: 0 error(s)
markdownlint exit 0
```

## T8 — Security (abuse cases 1–3)

Abuse case 1 — markup and `**` / backtick payloads in transcript text render as text:
`components/primitives.test.tsx › renders attacker-shaped text as text` and
`components/Transcript.test.tsx › renders attacker-shaped tool text as text, not markup`
(both green above). Abuse case 2 — an unknown stored theme is ignored:
`state/settings.test.ts › drops a value that is neither light nor dark`. Abuse case 3 — the
pre-paint script evaluates nothing from storage: reviewed (`ui/index.html`: one
`localStorage.getItem`, one `JSON.parse` inside `try`, two literal comparisons, one
`classList.toggle`), and the repository holds no HTML-injecting call:

```text
$ grep -rn "dangerouslySetInnerHTML\|innerHTML\|eval(" ui/src ui/index.html
grep exit 1
```

## T9 — Accessibility

Role and name contracts are asserted by the suite (`role="log"` + name + `tabindex` on the
trace, `aria-current` on rows / tabs / the current node, the `role="switch"` answering Enter
and Space, `<details>` disclosures collapsed by default). The reduced-motion guard:

```text
$ grep -n "prefers-reduced-motion" ui/src/styles/app.css
169:  @media (prefers-reduced-motion: reduce) {
```

## T5 — UI / visual (built app, demo fixture, headless Chromium)

Captured by `ui/scripts/screenshots.mjs` against `bun run preview` over `dist/`, in both
themes, at 1440×900 and 390×844. The prototype still each screen answers to is under
[`../design/screenshots/`](../design/screenshots/).

| # | Screen / state | Dark | Light | Prototype still |
|---|---|---|---|---|
| 01 | Home — nothing selected, the newest item (an armed item with no session: event-trail fallback) | [`01-home-dark.png`](01-home-dark.png) | [`01-home-light.png`](01-home-light.png) | `prototype-01-home-*.png` |
| 02 | Work item #214 — trace with tool groups and thinking, the agent's question banner, composer | [`02-item-214-dark.png`](02-item-214-dark.png) | [`02-item-214-light.png`](02-item-214-light.png) | `prototype-01-home-*.png` |
| 03 | Full graph — every node in one scrolling row | [`03-full-graph-dark.png`](03-full-graph-dark.png) | [`03-full-graph-light.png`](03-full-graph-light.png) | `prototype-04-full-graph-dark.png` |
| 04 | A tool group and one call expanded (input + result) | [`04-tools-expanded-dark.png`](04-tools-expanded-dark.png) | [`04-tools-expanded-light.png`](04-tools-expanded-light.png) | `prototype-07-toolcalls-expanded-dark.png` |
| 05 | Tool calls switch off | [`05-tools-off-dark.png`](05-tools-off-dark.png) | [`05-tools-off-light.png`](05-tools-off-light.png) | `prototype-06-toolcalls-off-light.png` |
| 06 | PR #216's session tab — human bubble, orphan output, the panel on the pull request | [`06-pr-session-dark.png`](06-pr-session-dark.png) | [`06-pr-session-light.png`](06-pr-session-light.png) | `prototype-03-tab-pr-41-dark.png`, `prototype-10b-aside-pr41-element-light.png` |
| 07 | Work item #205 — parked human gate: strip status, panel banner, Approve banner | [`07-gate-dark.png`](07-gate-dark.png) | [`07-gate-light.png`](07-gate-light.png) | `prototype-10-aside-element-dark.png` |
| 08 | Work item #187 — no session: transcript fallback notice + event trail, blocked composer with its reason | [`08-fallback-dark.png`](08-fallback-dark.png) | [`08-fallback-light.png`](08-fallback-light.png) | — (a state the prototype does not draw) |
| 09 | Standing sessions pane | [`09-standing-dark.png`](09-standing-dark.png) | [`09-standing-light.png`](09-standing-light.png) | — |
| 10 | Settings pane | [`10-settings-dark.png`](10-settings-dark.png) | [`10-settings-light.png`](10-settings-light.png) | — |
| 11 | Both side panels collapsed; reopen controls in the header | [`11-panels-closed-dark.png`](11-panels-closed-dark.png) | [`11-panels-closed-light.png`](11-panels-closed-light.png) | `prototype-08-sidebar-collapsed-light.png` |
| 12 | 390 px — panels start closed, the main column has the width | [`12-mobile-dark.png`](12-mobile-dark.png) | [`12-mobile-light.png`](12-mobile-light.png) | `prototype-19-mobile-390-dark.png` (the prototype's zero-width main, corrected here) |
| 12b | 390 px — the sidebar opened, overlaying the column | [`12b-mobile-sidebar-dark.png`](12b-mobile-sidebar-dark.png) | [`12b-mobile-sidebar-light.png`](12b-mobile-sidebar-light.png) | — |

The capture blocks nothing: the fonts load from Google Fonts as they do in production, and
the demo transport is selected through `localStorage` before the page loads. The one
console error in the run is the missing `favicon.ico`, which the prototype also lacks.

## Not run, and why

- **T3 contract / T4 end-to-end / T6 snapshot / T7 performance / T11 manual** — n/a per the
  plan: no API, route or model change (`ui/src/api/`, `ui/src/demo/` and every file under
  `ui/src/state/` but `settings.ts` are byte-identical); no live workstation service in this
  environment. The owner's review of the PR is the human pass.
