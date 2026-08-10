# Verification evidence: adoption precedes the spawn

> issue-201 · every row of [`bugfix.md`](../bugfix.md) § Testing. Captured 2026-08-10
> from the repository root.

## T1 — the ordering, asserted from inside `tmux.spawn`

```console
$ uv run --project cli python -m pytest cli/tests/test_harness_config_scaffold_integration.py -k before_the_harness -v --no-header
cli/tests/test_harness_config_scaffold_integration.py::test_the_repository_is_adopted_before_the_harness_is_started PASSED [100%]

======================= 1 passed, 9 deselected in 0.12s ========================
```

### The same test, with the pre-spawn call removed

A test of an ordering has to fail when the ordering is wrong, so the fix was reverted
in place and the test re-run before being kept:

```text
FAILED tests/test_harness_config_scaffold_integration.py::test_the_repository_is_adopted_before_the_harness_is_started
AssertionError: the harness was started in a checkout with no harness config —
adoption must precede tmux.spawn, not follow it (issue-201)
assert False is True
  where False = SpawnObserver.config_present_at_spawn
```

## T2 — the dispatcher call sequence

```console
$ uv run --project cli python -m pytest -q cli/tests/test_graph_drive_integration.py
.........                                                                [100%]
9 passed in 0.44s
```

## T3 — issue-193's suite, with adoption moved

```console
$ uv run --project cli python -m pytest -q cli/tests/test_harness_config_scaffold_integration.py cli/tests/test_harness_config.py
...............................................                          [100%]
47 passed in 0.84s
```

## T4 — whole suite

```console
$ make test
........................................................................ [ 96%]
.......................................................                  [100%]
1782 passed, 1 skipped in 75.09s (0:01:15)
```

## T5 — lint, format, type-check, schema validation

```console
$ make lint
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 548 file(s)
Summary: 0 error(s)
$ make format-check
uv run ruff format --check cli hooks
188 files already formatted
$ make typecheck
uv run pyright cli
0 errors, 0 warnings, 0 informations
$ make validate
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```
