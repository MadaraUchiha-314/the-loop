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

## Review round human-1 (PR #187): the uninitialized repository

Seven tests added for R6 (defaults with no `.the-loop/`; the walk in a never-adopted
git repo with the spec tree excluded — `git check-ignore` + clean `status
--porcelain`; adopted repos untouched; `publish-artifact` posting only where the
thread is the surface), then the full suite re-run:

```text
$ uv run pytest tests/test_graph_contribution.py -q
40 passed in 3.03s

$ uv run pytest -q
1565 passed, 1 skipped in 49.62s
```

## Lint and type checks

```text
$ uv run ruff check .
All checks passed!

$ uv run pyright
0 errors, 0 warnings, 0 informations

$ npx markdownlint-cli2 <the 16 changed/added markdown files>
Summary: 0 issues in 0 files
```
