# CI parity (T13)

Run on 2026-11-20 at `a0b978dd`, after the review fixes from the repository root, with the three
`THE_LOOP_*` variables unset.

| Row | Command | Result |
|---|---|---|
| T13 | `uv run pre-commit run --all-files` | exit 0 |

```text
ruff (lint + autofix)....................................................Passed
ruff (format)............................................................Passed
pyright (type check cli).................................................Passed
pytest (cli unit tests)..................................................Passed
markdownlint (all markdown, incl. docs)..................................Passed
validate .the-loop config against schema.................................Passed
```

The whole CLI suite inside that run: 7928 passed, 2 skipped.
