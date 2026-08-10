# Verification evidence: lint, format, type-check and schema validation

> issue-193 · row T13 of [`testing-plan.md`](../testing-plan.md). CI runs these same
> commands through pre-commit, so local and CI cannot disagree. Captured 2026-08-10.

## T13 — `make lint format-check typecheck validate`

```console
$ make lint
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 523 file(s)
Summary: 0 error(s)

$ make format-check
uv run ruff format --check cli hooks
185 files already formatted

$ make typecheck
uv run pyright cli
0 errors, 0 warnings, 0 informations

$ make validate
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```
