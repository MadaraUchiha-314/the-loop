---
type: evidence
workItem: issue-543
---

# CI parity: PR-scoped specs

> Testing-plan row T12, run at commit `08fba802` on 2026-11-19 from the repository root, with
> the daemon's `THE_LOOP_*` variables unset.

`make check` exited 0:

| Step | Result |
|------|--------|
| `ruff check cli hooks` | All checks passed |
| `markdownlint-cli2 "**/*.md"` | 0 errors |
| `ruff format --check cli hooks` | 535 files already formatted |
| `pyright cli` | 0 errors, 0 warnings |
| `pytest -q` | 7176 passed, 3 warnings in 254.65s |

**Run with the daemon's variables set,** 22 tests in `test_poll_status.py` and
`test_poll_command.py` failed: they read this machine's live instance. With the variables
unset, as in CI, they pass. None of them touches code this change edits.

## Re-run after the reviews

At `4372de01`, after the self-review, critic and security fixes: `make check` exits 0,
with 7200 passed, pyright at 0 errors and ruff clean. It was run with
`THE_LOOP_INSTANCE`, `THE_LOOP_WORK_ITEM` and `THE_LOOP_CLI_CONFIG` unset, as before.
