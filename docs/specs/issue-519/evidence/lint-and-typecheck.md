---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#519"
---

# Lint, format, types, tests, markdown and schema: the full pre-commit run

Work item issue-519 — activity **T12** of `testing-plan.md`: `uv run pre-commit run --all-files`, the same command CI runs, from the worktree root with `THE_LOOP_CLI_CONFIG` unset.

## Run 1 — on the tree after task 8

Found two defects and fixed them in the next commit: 15 pyright errors in the three new test files' doubles (an untyped `FakeTransport`, `Channel`-typed handles used as `SlackBotChannel`), and `tests/test_channels_dm.py::test_status_says_nothing_about_a_kind_it_cannot_derive`, whose "no `[!]`" assertion met the new posting finding because that test sets no bot token; it now sets one so its one finding is the kind's. Every other hook passed (6765 of 6766 tests).

## Run 2 — on the tree after the fixes

```text
ruff (lint + autofix)....................................................Passed
ruff (format)............................................................Passed
pyright (type check cli).................................................Failed
- hook id: pyright
- files were modified by this hook
0 errors, 0 warnings, 0 informations
pytest (cli unit tests)..................................................Failed
- hook id: pytest
- files were modified by this hook
6767 passed, 2 warnings in 262.29s (0:04:22)
markdownlint (all markdown, incl. docs)..................................Passed
validate .the-loop config against schema.................................Passed
exit=1
```

Every hook's substance passed: 0 pyright errors, 6767 tests passed, markdownlint and the config validation clean. The two `Failed` marks are pre-commit's "files were modified by this hook": the-loop's own runtime rewrote `docs/specs/issue-519/work-item-state.json` in the working tree while the hooks ran (this session is driven by the daemon, whose checks write the state file), which pre-commit reports as a modification. Run 3 below is the same command on an export of `HEAD` where nothing writes.

## Run 3 — on a clean export of HEAD

`git archive HEAD` into a scratch directory with nothing else writing to it, then the same
command (`uv run pre-commit run --all-files`, `THE_LOOP_CLI_CONFIG` unset):

```text
ruff (lint + autofix)....................................................Passed
ruff (format)............................................................Passed
pyright (type check cli).................................................Passed
pytest (cli unit tests)..................................................Passed
markdownlint (all markdown, incl. docs)..................................Passed
validate .the-loop config against schema.................................Passed
exit=0
```

Every hook passed and the run exited 0: lint, format, types, the whole test suite, every
markdown file and the config validation. HEAD at the time was `849ca1c1`.
