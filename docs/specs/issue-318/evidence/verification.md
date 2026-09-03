# Verification — issue-318

> The testing plan executed (`testing-plan.md`, rows T1, T2, T8, T10, T12). Commands run
> from the repository root at the head of `claude/github-issue-318-m5e70p`. Every token
> in the tests is a fixture (`xoxb-test-000000000000`, `xoxb-not-a-real-token-…`);
> nothing here needed redaction.

## Red → green, per task

The tests for tasks 1–4 were written first and run against `31b1183`:

```text
uv run --project cli python -m pytest -q cli/tests/test_envfile.py cli/tests/test_envfile_integration.py
ImportError while importing test module 'cli/tests/test_envfile.py'.
cli/tests/test_envfile.py:16: in <module>
    from the_loop import cli_config, envfile
E   ImportError: cannot import name 'envfile' from 'the_loop'
1 error in 0.15s

uv run --project cli python -m pytest -q cli/tests/test_envfile_integration.py
----------------------------- Captured stdout call -----------------------------
the-loop 13.2.0
=========================== short test summary info ============================
FAILED cli/tests/test_envfile_integration.py::test_the_slack_token_comes_from_the_env_file_the_config_names
1 failed, 1 passed in 0.09s
```

| Task | Red (before the change) | Green |
|------|-------------------------|-------|
| 1 loader | `test_envfile.py` — collection error: no `the_loop.envfile` | 12 passed (grammar, loader) |
| 2 resolver + schema | the same collection error; `resolve_env_file` / `load_env_file` absent | 7 passed; `test_config_schema_parity.py`, `test_docs_parity.py` green after the docs |
| 3 entry points | `test_envfile.py` — the three entry-point tests | 3 passed |
| 4 scenario | `test_envfile_integration.py` — 1 failed (`KeyError: THE_LOOP_SLACK_BOT_TOKEN`), 1 passed (the exported value was untouched because nothing loaded) | 2 passed |
| 5 docs | — | `make check` (markdownlint, docs parity) below |

One requirement caught by its own test on the way to green:
`test_a_stale_or_broken_config_loads_nothing_and_does_not_raise` failed against the first
implementation, which read the config leniently **without** the version gate and so loaded
the env file for a config the command was about to refuse (R2.6). The loader now runs
`assert_current` and loads nothing for a stale config.

## Rows T1, T2, T8, T10

```text
== T1
45 passed in 0.40s
== T2
2 passed in 0.11s
== T8
5 passed, 3016 deselected in 1.89s
== T10
53 passed, 19 deselected in 0.19s
```

## Config validation (T10, `make validate`)

```text
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

## `make check` — the way CI runs it (T12)

```text
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/** !docs/specs/*/design/**
Linting: 957 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
277 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
uv run --project cli python -m pytest -q cli
........................................................................ [  2%]
…
3020 passed, 1 skipped in 133.74s (0:02:13)
exit=0
```

Three self-review passes over the diff (recorded in `execution-log.md`): the loader's
config read was made strict and silent so a broken config is reported once, by the
command, not twice; the requirement above (R2.6) was enforced; pass three found nothing
new. `make check` was re-run after the last change: `ruff check` / `ruff format
--check` / `pyright` clean, and `test_envfile.py`, `test_envfile_integration.py`,
`test_cli_config.py` — 47 passed.
