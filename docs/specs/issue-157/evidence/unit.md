# Evidence — unit and integration tests (issue-157)

> Committed with the work item per the loop's evidence rule. Every command below
> was run from the repository root on 2026-08-06. No credentials, no network: the
> install tests drive a fake `PATH`, a fake HOME under `tmp_path` and a recording
> runner, so no real `git`, `claude` or `cursor-agent` is started.

## T1 — the plan/execute unit suite, red first (TDD)

Task 1 landed the Cursor tests before the component existed:

```text
FAILED cli/tests/test_install.py::test_the_cursor_clone_lives_under_the_documented_path
FAILED cli/tests/test_install.py::test_components_all_selects_every_component_even_when_undetected
22 failed, 40 passed in 0.36s
```

Task 2 turned them green, and the self-review round added two more
(the docs-parity guard on the clone path, and R1.4 for a skipped Cursor) —
`uv run --project cli python -m pytest -q cli/tests/test_install.py`:

```text
................................................................         [100%]
64 passed in 0.23s
```

## T8 — the security / abuse-case subset

`uv run --project cli python -m pytest -q cli/tests/test_install.py -k "invalid or dry_run or project or occupied or exactly"`:

```text
.....................                                                    [100%]
21 passed, 43 deselected in 0.05s
```

## T2 — the integration scenarios

`uv run --project cli python -m pytest -q cli/tests/test_install_integration.py`:

```text
.............                                                            [100%]
13 passed in 0.27s
```

## T1/T2/T8/T10 — the full suite (no regression from the dispatch change)

`make test`:

```text
........................................................................ [ 94%]
.......................................................................  [100%]
1366 passed, 1 skipped in 41.41s
```
