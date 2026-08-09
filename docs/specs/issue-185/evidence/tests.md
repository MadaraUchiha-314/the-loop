# Evidence: issue-185 verification runs

> Captured 2026-08-09 in the work item's own checkout (`cli/`, via `uv run`).
> Nothing redacted — no tokens, hostnames or personal data appear in these outputs.

## Red → green

The suite was written against the design before the parser handled bold-wrapped
markers; the red run is the TDD record, the fix followed, then green.

### Red (first run of the new suite)

```text
FAILED tests/test_graph_contribution.py::test_parse_goal_tolerates_markdown_decoration
1 failed, 5 passed in 0.13s
```

(Two later reds in the same session — the thread-path authorization mismatch between
bare API logins and `@`-prefixed allowlists — are recorded in the execution log; both
fixed in `goal.py`, never by weakening a test.)

### Green — the new suite

```text
$ uv run pytest tests/test_graph_contribution.py -q
33 passed in 1.48s
```

## Full suite

```text
$ uv run pytest -q
1558 passed, 1 skipped in 47.63s
```

The one skip pre-exists this work item (environment-dependent, unrelated).

## Lint and type checks

```text
$ uv run ruff check .
All checks passed!

$ uv run pyright
0 errors, 0 warnings, 0 informations

$ npx markdownlint-cli2 <the 16 changed/added markdown files>
Summary: 0 issues in 0 files
```
