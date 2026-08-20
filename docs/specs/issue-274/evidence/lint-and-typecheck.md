# Static analysis — lint, format, types, config (issue-274)

Every check clean on its first run after the change. Same tools CI runs (`make lint`,
`make format-check`, `pyright`, `scripts/validate_config.py` — the pre-commit set).

## `make lint`

```console
$ uv run ruff check cli hooks
All checks passed!
$ npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 838 file(s)
Summary: 0 error(s)
```

838 markdown files: 836 before, plus this work item's two new documents that lint
(`docs/specs/issue-274/*`, `docs/decisions/decision-098.md`).

## `make format-check`

```console
$ uv run ruff format --check cli hooks
250 files already formatted
```

## Types

```console
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
```

## Config schema validation

```console
$ uv run python scripts/validate_config.py
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

No schema changed in this work item — the operation adds no configuration key — so this
run is a no-change control.
