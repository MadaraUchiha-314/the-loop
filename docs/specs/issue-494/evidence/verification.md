# Verification: issue-494

Run on 2026-10-16, in this checkout (`fix/issue-494-brainstorm-approval`), with Python
through `uv`. No credentials were used: GitHub calls in the tests go through the
suite's fakes.

## Verification results

| Activity | Command | Outcome |
|----------|---------|---------|
| T1–T6 on the branch | `cd cli && uv run python -m pytest -q tests/test_brainstorm_gate_integration.py tests/test_graph_integration.py tests/test_graph_hooks.py tests/test_graph_skips.py tests/test_core_graphs.py tests/test_gate_pointer_integration.py tests/test_pdlc_e2e_integration.py tests/test_jira_format.py tests/test_jira_integration.py` | pass |
| Regression tests red before the fix | the new tests run with `origin/main`'s `pdlc-work-item-loop.yaml`, `hooks/artifacts.py` and `hooks/feedback.py` checked out | **9 failed**, 2 passed (the 2 are the "unchanged without the parameter" tests, which pass on `main` by design) |
| The same tests on the branch | same selection | 11 passed |
| T7 lint, format, types, config | `make lint format-check typecheck validate` | pass: ruff clean, 452 files formatted, pyright 0 errors, markdownlint 0 errors, `validate` exit 0 |
| T7 full suite | `make test` (`cd cli && uv run python -m pytest -q`) | 6125 passed, 21 failed |
| T7 baseline on the base commit (`584958c`, `origin/main`) | same command, before any change | 6116 passed, **the same 21 failed** |

## About the 21 failures

All 21 also fail on the base commit in this environment, and none touches the graph:
`test_poll_status.py` (13), `test_poll_command.py` (4), `test_instances_cmd.py` (2),
`test_lifecycle_cmd.py` (1) and `test_critics.py` (1). They read the machine's live poller pidfile and the operator's own
`cli-config.yaml`, because a the-loop poller is running on the host that ran them. CI
runs them on a clean runner.

## Notes against the plan

- T5: the e2e scenarios needed no edits. A declared-skipped `brainstorming` routes on
  `skipped` straight to `requirements-definition`, so `brainstorm-approval` never
  appears in their exact node traces, which is the behaviour R2.2 asks for.
- T3 found a defect the design had missed: `check --recompute` scores every node in
  declaration order rather than walking edges, so the new gate read as an unmet
  `wait` for an item with no brainstorm (`test_gate_pointer_integration.py`, 6 tests).
  It is fixed by `classify-feedback`'s opt-in `whenPresent: brainstorm.md`, and pinned
  by `test_a_skipped_brainstorm_never_reaches_its_gate` and
  `test_when_present_skips_a_gate_whose_subject_was_never_written`.
