---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#503"
---

# Lint, types and the whole suite (T11)

Every pre-commit hook passed: ruff lint and format, pyright, the full pytest suite,
markdownlint and the `.the-loop` config validation. The run used the clean environment
described in [unit.md](unit.md).

The first run inherited the session's `THE_LOOP_CLI_CONFIG`, and 21 tests failed in
unrelated files (`test_poll_status.py` and others). With that variable unset, all of them
pass.

## `uv run pre-commit run --all-files`

```text
ruff (lint + autofix)....................................................Passed
ruff (format)............................................................Passed
pyright (type check cli).................................................Passed
pytest (cli unit tests)..................................................Passed
markdownlint (all markdown, incl. docs)..................................Passed
validate .the-loop config against schema.................................Passed
```
