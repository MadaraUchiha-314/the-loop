# Evidence: verification

Executed 2026-09-02 on `claude/the-loop-architecture-h5cfh9`, Python 3.11, `uv 0.8.17`.
Nothing here needed a credential; the Slack SDK client and the `gh` writers are faked at
their injection points in every test.

## T1 — unit

```text
$ uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_identity.py cli/tests/test_bus.py
81 passed in 0.30s
```

## T2 — integration scenarios

```text
$ uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py cli/tests/test_bus_integration.py
16 passed in 0.74s
```

## T8 — security / abuse cases

```text
$ uv run --project cli python -m pytest -q cli/tests -k "abuse or unauthorized or envelope or grant or kickoff"
76 passed, 2769 deselected in 9.44s
```

## T10 — migration / schema parity

```text
$ uv run --project cli python -m pytest -q cli/tests/test_migrations.py cli/tests/test_config_schema_parity.py cli/tests/test_configschema.py
91 passed in 2.33s
```

## T12 — `make check` (lint, format, typecheck, config validation, the full suite)

```text
$ make check
uv run ruff check cli hooks
All checks passed!
npx markdownlint-cli2 "**/*.md"
Summary: 0 error(s)
uv run ruff format --check cli hooks
271 files already formatted
0 errors, 0 warnings, 0 informations
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
2844 passed, 1 skipped in 163.29s (0:02:43)
```

Exit code 0.
