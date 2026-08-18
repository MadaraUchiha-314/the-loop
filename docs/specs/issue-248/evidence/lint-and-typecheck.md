# Evidence: lint and type check

Captured on 2026-08-18.

## Ruff + markdownlint

```text
$ make lint
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 807 file(s)
Summary: 0 error(s)
```

## Pyright

```text
$ make typecheck
uv run pyright cli
0 errors, 0 warnings, 0 informations
```

## Config validation against the changed schemas

```text
$ uv run --project cli --with jsonschema python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```
