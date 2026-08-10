# Evidence: lint, format and type check (issue-188)

The same commands CI runs (`make lint format-check typecheck validate`), from the project
root.

## `make lint` — ruff + markdownlint over every markdown file

```text
$ make lint
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 501 file(s)
Summary: 0 error(s)
```

## `make format-check` — CI parity with pre-commit's `ruff format`

```text
$ make format-check
uv run ruff format --check cli hooks
179 files already formatted
```

## `make typecheck`

```text
$ make typecheck
uv run pyright cli
0 errors, 0 warnings, 0 informations
```

## `make validate` — the config files against their schemas

```text
$ make validate
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```
