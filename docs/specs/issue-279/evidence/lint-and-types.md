# Evidence: lint, formatting, types, config validation

Captured 2026-08-24, on the work item's branch, from the repository root.

```console
$ uv run ruff check cli hooks
All checks passed!

$ uv run ruff format --check cli hooks
259 files already formatted

$ uv run pyright cli
0 errors, 0 warnings, 0 informations

$ npx markdownlint-cli2@0.18.1 "**/*.md"
Linting: 870 file(s)
Summary: 0 error(s)

$ uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```
