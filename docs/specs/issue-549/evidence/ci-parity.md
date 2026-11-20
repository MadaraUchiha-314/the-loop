# CI parity (T12)

Run on 2026-11-20 at `5d90a8b1` (before the live-test
fix, which changed one test file; that file then passed the same hooks with
`--files`). From the repository root, with the three variables unset:

```text
uv run pre-commit run --all-files
ruff (lint + autofix) Passed
ruff (format) Passed
pyright (type check cli) Passed
pytest (cli unit tests) Passed
markdownlint (all markdown, incl. docs) Passed
validate .the-loop config against schema Passed
```

Exit code 0. The pytest hook runs the whole suite.
