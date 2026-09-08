# Verification — issue-321

> The testing plan executed (`testing-plan.md`, rows T1, T2, T8, T10, T12). Commands run
> from the repository root at the head of `claude/github-issue-321-tipucc`. Every
> token in the tests is a fixture (`xoxb-test`); the checkouts are `git init` temp
> directories with a `https://github.com/o/r.git` origin. Nothing here needed
> redaction.

## The reproduction, before the change

A scratch script against `ba0c433` (13.3.0): a real checkout with `origin`, a registry
record whose `cwd` is that checkout, `graph-state.json` parked at
`requirements-approval`, a `start` recorded in the portable control store, the default
control policy. The dispatcher's coupling and the pipeline's read, over the same config:

```text
dispatcher sees gate: True
pipeline sees gate: False
```

## Red → green, per task

The two T2 scenarios (task 1) were written first and run against `ba0c433`:

```text
uv run --project cli python -m pytest -q cli/tests/test_bus_integration.py -k "default_control_policy or no_session_record"
E       AssertionError: assert (1 == 1 and [('github:o/r#7', 'approved')] == []
E         Left contains one more item: ('github:o/r#7', 'approved')
FAILED cli/tests/test_bus_integration.py::test_an_approval_from_slack_reaches_the_gate_under_the_default_control_policy
FAILED cli/tests/test_bus_integration.py::test_a_reply_for_a_work_item_with_no_session_record_is_left_to_the_ledger
2 failed, 8 deselected in 0.17s
```

The failure is the bug in one line: the pipeline classified the approval as a
`work-item.reply` and **delivered it into the session** (the marked mirror, invisible to
the gate) instead of leaving it, unmarked, to the ledger.

| Task | Red (before the change) | Green |
|------|-------------------------|-------|
| 1 reproduction | 2 failed (above) | 10 passed (`test_bus_integration.py`) |
| 2 reader | `_graph_reader` absent; `_at_human_gate` returned `False` for a missing record | `test_the_pipeline_reads_the_graph_through_the_dispatchers_own_coupling`, `test_no_session_record_is_an_unknown_gate_not_a_closed_one`, `test_a_disabled_graph_coupling_means_no_gate_to_answer`, `test_the_pipelines_read_moves_nothing`, `test_a_graph_fault_is_cannot_tell` |
| 3 classification + record + event | `classify` took no grants; `channel.reply_received` carried no `gate` | the remaining six T1 tests |
| 4 docs | — | `make lint` (markdownlint over 965 files), `test_docs_parity.py` |

## Rows T1, T2, T8, T10

```text
== T1
73 passed in 0.45s
== T2
10 passed in 0.20s
== T8
5 passed, 68 deselected in 0.07s
== T10
8 passed in 0.12s
```

## Row T12 — `make check`

`make lint`:

```text
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 965 file(s)
Summary: 0 error(s)
```

`make format-check`, `make typecheck`, `make validate`:

```text
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
```

`make test` (the full suite):

```text
uv run --project cli python -m pytest -q cli
3033 passed, 1 skipped in 156.64s (0:02:36)
```

The first `make lint` run found two unused imports in the new tests (ruff F401) and the
first `format-check` two files to reformat; both fixed and re-run, as recorded above.
No existing assertion was changed: the eight issue-309 scenarios that patch
`_at_human_gate` to `True` / `False` pass unchanged against the three-valued read.
