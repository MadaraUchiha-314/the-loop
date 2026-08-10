# Evidence — the full check (T6, T14)

Work item: issue-199 · captured 2026-08-10.

## `make check` — lint, markdown, format, typecheck, config validation, the whole suite

The same commands CI runs (`make check` = `lint format-check typecheck validate test`).
Exit code `0`.

```text
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 539 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
188 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
uv run --project cli python -m pytest -q cli
1770 passed, 1 skipped in 79.14s (0:01:19)
```

## The regression question this row exists for (T6)

The spawn path now runs an exit chain that never ran there before, so the whole suite is
the check that nothing else moved. Baseline before the change: **1760 passed, 1 skipped**
(plus one pre-existing double that had to learn the new `routed` argument —
`test_graph_drive_integration.py::_SeqLink`, recorded as an unplanned change in
`tasks.md`). After: **1770 passed, 1 skipped** — the ten new cases, no other change of
verdict.

`test_docs_parity.py` (T14) passes as part of the run: it is what holds the changed
`docs/cli/commands/graph.md` to the shipped command surface.
