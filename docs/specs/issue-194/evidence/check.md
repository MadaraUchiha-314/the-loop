# Evidence — the full check (T4, T13) and the red→green record

Work item: issue-194 · captured 2026-08-10.

## `make check` — lint, format, typecheck, config validation, the whole suite

The same commands CI runs (`make check` = `lint format-check typecheck validate test`).
Exit code `0`.

```text
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 523 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
187 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
uv run --project cli python -m pytest -q cli
....                                                                     [100%]
1731 passed, 1 skipped in 76.68s (0:01:16)
```

### Suite totals

| | Tests | Skipped |
|---|---|---|
| Baseline (`origin/main`, before this work item) | 1686 | 1 |
| This branch | 1731 | 1 |

The 45 added tests are the two new files: 33 unit (`test_graph_refs.py`) and 12
integration (`test_graph_refs_integration.py`). No existing test changed.

## Red→green

The regression evidence R1.6 and R2.7 ask for. `cli/the_loop` was stashed back to the
9.5.0 source (`git stash push --include-untracked -- cli/the_loop`) with both new test
files left in place, and the integration file — which imports nothing that did not already
exist — was run against it:

```text
$ git stash push --include-untracked -- cli/the_loop
$ uv run --project cli python -m pytest -q cli/tests/test_graph_refs_integration.py
------------------------------ Captured log call -------------------------------
WARNING  the-loop.graph:runtime.py:1046 could not post the skip audit comment: github is down
=========================== short test summary info ============================
FAILED cli/tests/test_graph_refs_integration.py::test_a_verb_with_no_ref_posts_to_the_repository_the_config_declares
FAILED cli/tests/test_graph_refs_integration.py::test_a_repo_with_no_ticketing_config_derives_nothing
FAILED cli/tests/test_graph_refs_integration.py::test_an_inner_loop_derives_the_pull_requests_ref_not_the_work_items
FAILED cli/tests/test_graph_refs_integration.py::test_a_failing_hook_is_reported_without_changing_the_edge
FAILED cli/tests/test_graph_refs_integration.py::test_a_force_whose_audit_comment_fails_says_so
FAILED cli/tests/test_graph_refs_integration.py::test_a_skip_whose_audit_comment_fails_says_so
FAILED cli/tests/test_graph_refs_integration.py::test_cli_advance_prints_the_warning
FAILED cli/tests/test_graph_refs_integration.py::test_cli_skip_prints_the_warning
8 failed, 4 passed in 0.94s
```

Eight of the twelve scenarios fail on the pre-fix source, each on the behaviour it was
written for. The four that pass are the ones asserting behaviour this work item did not
change: an explicit `--ref` winning, an inner loop with no derivable ref falling back to
the bare id, a healthy run printing no warning, and an idempotent re-entry staying quiet.

`test_graph_refs.py` cannot be run this way — it imports `the_loop.graph.refs`, which did
not exist — so its red signal is a `ModuleNotFoundError` rather than a failing assertion.
That is why the behavioural red→green is measured on the integration file.
