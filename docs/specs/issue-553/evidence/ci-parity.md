# CI parity evidence — issue-553

`make check`, the command CI runs, at the documentation commit. Exit code 0.

| Step | Result |
|---|---|
| `ruff check cli hooks` | All checks passed |
| `markdownlint-cli2 "**/*.md"` | 0 errors |
| `ruff format --check` | passed |
| `pyright` | 0 errors, 0 warnings |
| config validation | passed |
| `cd cli && uv run python -m pytest -q` | 7979 passed, 2 skipped |

The run unset this daemon session's `THE_LOOP_INSTANCE`, `THE_LOOP_WORK_ITEM` and
`THE_LOOP_CLI_CONFIG`. With them set, about 45 unrelated tests (poller status,
stop-check, instances) read the live daemon's state and fail. CI does not set them.
