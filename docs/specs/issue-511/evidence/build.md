---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#511"
---

# Build, bundle and untouched directories (T12): de-cluttering the control plane UI

> Run at `verification` on 2026-10-20.

## Build

```text
cd ui && bun run build
$ tsc --noEmit && vite build
dist/index.html                   2.05 kB │ gzip:   0.95 kB
dist/assets/index-DGFyk9GC.css   24.42 kB │ gzip:   5.76 kB
dist/assets/index-DHxDxucx.js   337.16 kB │ gzip: 102.35 kB │ map: 1,441.04 kB
✓ built in 1.29s
```

## Bundle against the branch point (NFR: removal must not grow it)

| Asset | 20.5.1 (branch point) | This branch | Change |
|---|---|---|---|
| JS | 341 685 B | 337 157 B | −4 528 B |
| CSS | 24 469 B | 24 421 B | −48 B |

The CSS first grew by a few hundred bytes from new utility classes on the popover and
the header; the summary's marker, a separator span and five utilities were replaced by
classes the app already used (commit `46a85e2`), which brought it under the baseline.

**Re-run after self-review round 1** (dead code removed: the panel column, the open-panel
button path, three icons, a dead composer prop): `bun run build` clean; JS 336 728 B,
CSS 24 350 B — smaller again.

## Untouched directories (R5.1)

```text
git diff --stat origin/main -- ui/src/api ui/src/state ui/src/demo
(empty)
```

No dependency was added: `ui/package.json` and `ui/bun.lock` are unchanged; Playwright
for the screenshot run was installed without saving, as `ui/scripts/screenshots.mjs`
documents.
