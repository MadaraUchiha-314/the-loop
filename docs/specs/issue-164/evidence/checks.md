# Evidence: lint, format, type-check and config validation

Work item: issue-164 · the "all" row of [`../testing-plan.md`](../testing-plan.md).

## Lint (ruff + markdownlint)

```console
make lint
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 432 file(s)
Summary: 0 error(s)
```

## Format check

```console
make format-check
uv run ruff format --check cli hooks
166 files already formatted
```

## Type check

```console
make typecheck
uv run pyright cli
0 errors, 0 warnings, 0 informations
```

## Config validation

Unchanged by this work item — no schema key and no config option was added
([`../design.md`](../design.md) §Data models) — and run to prove exactly that.

```console
make validate
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```
