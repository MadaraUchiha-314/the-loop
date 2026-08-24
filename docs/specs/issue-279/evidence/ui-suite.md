# Evidence: the UI suite (T5)

Captured 2026-08-24, on the work item's branch, from `ui/`.

```console
$ bun run lint
$ oxlint --type-aware      # clean

$ bun run test
 Test Files  12 passed (12)
      Tests  157 passed (157)

$ bun run build
dist/assets/index-Iowr0hRB.css   29.93 kB │ gzip:  5.76 kB
dist/assets/index-BtaWvIS3.js   287.61 kB │ gzip: 88.45 kB │ map: 1,255.20 kB
✓ built in 1.31s
```

The treeless-rendering test (`ui/src/api/model.test.ts` § "flags ad-hoc, contribution
and review loops treeless") now iterates `pdlc-review-loop` as the third name; the count
stays 157 because the three loops share one test body. The `ADHOC_LOOPS` set and the
`SessionTreeItem.adhoc` flag were renamed `TREELESS_LOOPS` / `treeless` — three loops in
a set named after one was a misreading waiting to happen.
