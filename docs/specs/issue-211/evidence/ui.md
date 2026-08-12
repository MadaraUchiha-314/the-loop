# Evidence: the dashboard's own gates (T15)

Captured 2026-08-12 in `ui/`. The change here is copy, not behaviour: three strings that
asserted the service sends no CORS headers, and the test that pinned the old advice.

```console
$ bun run test
 ✓ src/api/client.test.ts (7 tests)
 ✓ src/api/model.test.ts (28 tests)
 ✓ src/state/settings.test.ts (7 tests)
 ✓ src/App.test.tsx (8 tests)

 Test Files  4 passed (4)
      Tests  50 passed (50)

$ bun run lint
$ oxlint --type-aware

$ bun run typecheck
$ tsc --noEmit
```

`client.test.ts`'s cross-origin case now asserts the advice names
`service.cors.allowOrigins` and points at Settings, rather than merely matching `/CORS/` —
the old assertion would have passed against the old, now-wrong sentence.
