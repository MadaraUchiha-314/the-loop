# Evidence — lint, format, types, schema and markdown (issue-183)

Activity T13 of the testing plan, run from the repository root. Same commands CI runs
(via pre-commit) — local == CI is the-loop's own rule.

```console
$ uv run ruff check cli hooks
All checks passed!

$ uv run ruff format --check cli hooks
173 files already formatted

$ uv run pyright cli
0 errors, 0 warnings, 0 informations

$ uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml

$ npx markdownlint-cli2 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 479 file(s)
Summary: 0 error(s)
```
