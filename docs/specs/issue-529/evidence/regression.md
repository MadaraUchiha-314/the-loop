---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#529"
---

# Regression (T12): `uv run pre-commit run --all-files`

Run with the session's `THE_LOOP_*` variables unset (see `unit.md`).

```text
ruff (lint + autofix)....................................................Passed
ruff (format)............................................................Failed
pyright (type check cli).................................................Passed
pytest (cli unit tests)..................................................Failed
markdownlint (all markdown, incl. docs)..................................Passed
validate .the-loop config against schema.................................Passed
6803 passed, 4 warnings in 228.39s (0:03:48)
```

`ruff (format)` reported *Failed* because it reformatted the new assertions in
`tests/test_channels_buttons.py`. The pytest hook reports *Failed* whenever an earlier
hook modified files. Every test passed (6803). The reformat is committed with this
evidence, and the rerun below is clean.

## Rerun after committing the reformat

```text
ruff (lint + autofix)....................................................Passed
ruff (format)............................................................Passed
pyright (type check cli).................................................Passed
pytest (cli unit tests)..................................................Passed
markdownlint (all markdown, incl. docs)..................................Passed
validate .the-loop config against schema.................................Passed
```
