# Evidence — `make check`

The whole gate, run the way CI runs it: lint (ruff + markdownlint over every `.md`),
format check, pyright, config validation, and the full suite.

```text
$ make check
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 511 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
183 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
uv run --project cli python -m pytest -q cli
1686 passed, 1 skipped in 72.86s (0:01:12)
```

**1650 → 1686**: 36 tests added, none removed, none skipped beyond the one this repository
already skips. The baseline was recorded before any code was written:

```text
$ uv run --project cli python -m pytest -q cli      # before this work item
1650 passed, 1 skipped in 61.67s (0:01:01)
```

One existing test changed: `test_daemon_status_not_running` asserted the daemon-status
dictionary by equality, so the three keys `daemon_status` now carries (`logfile`,
`startedAt`, `lastCycleAt`) had to be added to its expectation. That is the assertion doing
its job — an added field is a contract change, and it made itself visible.
