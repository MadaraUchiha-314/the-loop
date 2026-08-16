# Evidence: the green run — UI (T2)

The dashboard's own toolchain, the three commands `.github/workflows/ci.yml` runs in `ui/`.
Run 2026-08-16 on `claude/github-issue-238-cwdgone`, after task 4.

## Lint (oxlint, type-aware)

```console
$ cd ui && bun run lint
$ oxlint --type-aware
(no output; exit 0)
```

No findings. (An earlier run flagged two unnecessary `as` assertions in the new test file;
both removed rather than suppressed.)

## Tests (vitest)

```console
$ cd ui && bun run test
 Test Files  8 passed (8)
      Tests  106 passed (106)
   Start at  19:19:04
   Duration  4.52s (transform 453ms, setup 2.88s, collect 1.03s, tests 3.57s, environment 6.27s, prepare 673ms)
```

The case that was red in [`red.md`](red.md) — `fetchGraphs` storing an answer it should
drop — now passes, and its sibling (a normal answer is stored) still does. 105 tests
passed before this work item and 106 pass now: the new file adds two cases and removes
none.

## Build (`tsc --noEmit`, then Vite)

```console
$ cd ui && bun run build
dist/index.html                   0.64 kB │ gzip:  0.38 kB
dist/assets/index-uvl1WAx4.css   26.88 kB │ gzip:  5.24 kB
dist/assets/index-CLSe7QFa.js   269.54 kB │ gzip: 83.10 kB │ map: 1,180.87 kB
✓ built in 575ms
```

`build` runs the type check first, so this covers the `repoResolved?: boolean` addition to
`GraphStatus` and the `=== false` comparison against it. During the red phase this step was
failing — the test referenced a field the type did not have — which is why it appears here
green rather than in `red.md` as a separate failure.
