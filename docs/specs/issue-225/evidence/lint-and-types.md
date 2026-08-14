# Evidence: lint, formatting, types and config validation

The repository's own gates (`hooks.preCommit`/`prePush`: lint, typecheck, unit-test),
run as `make` runs them so local matches CI.

## ruff — lint

```console
$ uv run ruff check cli hooks
All checks passed!
```

## ruff — formatting

```console
$ uv run ruff format --check cli hooks
208 files already formatted
```

## pyright — types

```console
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
```

## markdownlint

```console
$ npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 639 file(s)
Summary: 0 error(s)
```

## schema validation

```console
$ uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

`skills/the-loop/templates/cli-config.yaml` now carries the new `do` keyword and still
validates against `.the-loop/cli-config.schema.json`, which is what proves the new
schema leaf and the template agree.
