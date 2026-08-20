# Evidence: lint, format, types, markdown and config validation (issue-277)

## `make lint` — ruff

```text
All checks passed!
```

## `make lint` — markdownlint

```text
Summary: 0 error(s)
```

## `make format-check`

```text
257 files already formatted
```

## `make typecheck` — pyright

```text
0 errors, 0 warnings, 0 informations
```

## `make validate` — every config against its schema

The `standingSessions` block this work item adds is validated here in three places: this
repository's own config, the shipped template, and (through the packaged copy) whatever an
operator writes.

```text
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```
