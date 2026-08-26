# issue-298 — verification evidence

The change is presentation-only, so the proof is: the existing behaviour suite still
passes untouched surfaces, the same three commands CI and the Pages publish run come
back clean, and the rendered screens match the signed-off design
([`../design/`](../design/)). Captured 2026-08-26 on `claude/github-issue-298-pi4sfr`.

## Lint (oxlint, type-aware)

```text
$ bun run lint
$ oxlint --type-aware
(exit 0, no findings)
```

## Tests (vitest — unit + React, demo transport)

```text
$ bun run test
 Test Files  12 passed (12)
      Tests  168 passed (168)
```

Two tests were updated for retired presentation (the "Outer loop ·" heading became
the rail-role assertion; the question card's kicker is now "The loop asks"); every
behavioural assertion — sidebar rows, grouping, inbox actions, gate approval,
replies, transcript rendering, deep links, standing-session verbs, config editor —
is unchanged and green.

## Build (`tsc --noEmit`, then the production bundle)

```text
$ bun run build
✓ 54 modules transformed.
dist/index.html                   0.64 kB │ gzip:  0.38 kB
dist/assets/index-Dt6Em9Ye.css   30.72 kB │ gzip:  5.88 kB
dist/assets/index-0Fn8ZU8B.js   288.58 kB │ gzip: 88.98 kB
✓ built in 1.38s
```

## UI / visual (screenshots, demo fixture, 1440×900)

Captured from the Vite dev server in demo mode with headless Chromium:

| Screen | File | Design reference |
|---|---|---|
| Work — overview (inbox) | [`overview.png`](overview.png) | `Control Plane.dc.html` |
| Work — item detail (rail, trace, chat) | [`item.png`](item.png) | `Control Plane.dc.html` |
| Work — standing sessions | [`standing.png`](standing.png) | restyled, not in the export |
| Events | [`events.png`](events.png) | restyled, not in the export |
| Settings | [`settings.png`](settings.png) | `Settings.dc.html` |

## Not run, and why

- **Contract / integration / performance** — n/a: no API, route, model-join or
  control-verb change; `ui/src/api/`, `ui/src/state/` and `ui/src/demo/` are
  untouched.
- **Live-service pass** — no workstation service in this environment; the demo
  transport exercises the same record shapes and verbs.
