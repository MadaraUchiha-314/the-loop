# Evidence: repository gates (T3, T10, T12, T13, T14)

Captured 2026-08-12 on the work item's branch — the same commands CI runs
(`make check`), run individually so each row of the plan has its own output.

## Full Python suite — includes contract parity (T3), config loading (T10) and docs parity (T12)

```console
$ uv run --project cli python -m pytest -q cli
1819 passed, 1 skipped in 78.12s (0:01:18)
```

The count was 1801 before this work item; the 18 added are the two new files. The rows
that matter here pass unchanged: `test_api_contract_parity.py` (the served OpenAPI surface
still equals the authored contract — CORS adds no path, method or operationId),
`test_cli_config.py` / `test_migrations.py` (a config with no `service.cors` block loads,
and `CURRENT_CONFIG_VERSION` did not move), and `test_docs_parity.py` P3–P5 (each of the
five new schema leaves is documented with its Type and Default).

## Schema validation (T13)

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

Both CLI configs now carry the `service.cors` block explicitly and validate against the
amended schema, including its `additionalProperties: false`.

## Lint, format, types, markdown (T14)

```console
$ uv run ruff check cli hooks
All checks passed!

$ uv run ruff format --check cli hooks
191 files already formatted

$ uv run pyright cli
0 errors, 0 warnings, 0 informations

$ npx markdownlint-cli2@0.18.1 "**/*.md"
Linting: 576 file(s)
Summary: 0 error(s)
```
