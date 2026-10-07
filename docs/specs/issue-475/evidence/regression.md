---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#475"
---

# Regression (T9, issue-475)

Run on 2026-10-06 at `b5c1154` from the repository root, with the session's env vars
removed (see [`verification.md`](verification.md)).

```text
$ uv run pre-commit run --all-files --show-diff-on-failure
ruff (lint + autofix)....................................................Passed
ruff (format)............................................................Passed
pyright (type check cli).................................................Passed
pytest (cli unit tests)..................................................Passed
markdownlint (all markdown, incl. docs)..................................Passed
validate .the-loop config against schema.................................Passed
```

| Hook | Result |
|------|--------|
| ruff (lint + autofix) | passed |
| ruff (format) | passed |
| pyright (type check cli) | passed |
| pytest (cli unit tests) | passed |
| markdownlint (all markdown, incl. docs) | passed |
| validate .the-loop config against schema | passed |

No hook changed a file. The pytest hook prints no count, so the whole suite was also run
once on its own:

```text
$ cd cli && uv run python -m pytest -q
5950 passed, 1 warning in 198.46s (0:03:18)
```
