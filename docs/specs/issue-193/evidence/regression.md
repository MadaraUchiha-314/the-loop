# Verification evidence: whole-suite regression

> issue-193 · row T12 of [`testing-plan.md`](../testing-plan.md). Adoption now writes a
> file into checkouts that many existing tests build without one, so the whole suite is
> the row that proves nothing else moved. Captured 2026-08-10.

## T12 — `make test`

```console
$ make test
........................................................................ [ 88%]
........................................................................ [ 92%]
........................................................................ [ 96%]
............................................................             [100%]
1715 passed, 1 skipped in 72.68s (0:01:12)
```
