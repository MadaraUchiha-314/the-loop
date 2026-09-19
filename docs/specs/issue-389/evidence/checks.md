---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#389"
---

# Checks (T12): `make check`

> Row T12 of [`testing-plan.md`](../testing-plan.md) § Evidence plan. Run at the PR's head
> on 2026-09-19 from the repository root.

```text
$ make check
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Linting: 1243 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
330 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
(validate: the schema copies, the manifest, the graph)
uv run python -m pytest -q
4127 passed, 1 skipped in 158.82s (0:02:38)
```

The one skipped test is the suite's standing skip, unrelated to this change. After the
self-review rounds the whole suite is 4149 passed, 1 skipped (`uv run python -m pytest -q`
from `cli/`, 2026-09-19); the round-2 fix commit's message says 4145, which is off by one.
