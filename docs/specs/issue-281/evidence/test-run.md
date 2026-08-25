# Evidence: issue-281 verification run

Commands run from the repository root on 2026-08-25, on the branch delivering
[issue #281](https://github.com/MadaraUchiha-314/the-loop/issues/281). No secrets,
hostnames or credentials appear in any capture.

## Unit + integration + e2e tests

```console
$ cd cli && uv run pytest -q
2674 passed, 1 skipped in 114.50s (0:01:54)
```

The run includes the new `lock-artifacts` unit tests
(`tests/test_graph_integration.py`), the updated graph-shape assertions
(`tests/test_graph_model.py`, `tests/test_graph_verification_integration.py`), and the
reworked e2e scenario suite (`tests/test_pdlc_e2e_integration.py`) whose happy path
now emits **draft** fixtures and asserts they reach `implementation` locked by the
approval gates — the regression walk for AC 1.5. The skip is the suite's usual
plugin-tree-absent guard, unrelated to this change.

## Lint

```console
$ cd cli && uv run ruff check
All checks passed!

$ cd cli && uv run ruff format --check .
258 files already formatted
```

## Type check

```console
$ cd cli && uv run pyright
0 errors, 0 warnings, 0 informations
```

## Markdown lint (changed documents)

```console
$ npx --yes markdownlint-cli2@0.18.1 "docs/specs/issue-281/*.md" \
    "docs/capabilities/{process-graph,spec-workflow,design-artifacts}.md" \
    "skills/the-loop/SKILL.md" "skills/the-loop/reference/*.md" \
    "skills/the-loop/templates/*.md" "commands/*.md" README.md \
    "docs/guide/what-is-the-loop.md"
Summary: 0 error(s)
```
