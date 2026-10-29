# Verification — issue-525

No testing plan: `test-planning` was skipped at phase selection, so this record stands
in for it.

## Verification results

| Activity | Command | Outcome |
|----------|---------|---------|
| New unit tests: an event leaves an agent node alone (`on_event`, `on_pr_event`), still reaches a human gate, still advances an unplaced pointer | `cd cli && uv run python -m pytest -q tests/test_graphlink.py` | pass |
| New integration tests over the real graphs: a CI event on the review loop's `review` step leaves it on `review` with nothing posted; a CI event on `implementation` spends no attempt | `cd cli && uv run python -m pytest -q tests/test_graphlink_integration.py` | pass |
| The new tests fail without the fix (graphlink.py swapped back to `HEAD~`) | same two files | 4 failed, 72 passed — the four new agent-node tests |
| Full suite | `cd cli && uv run python -m pytest -q` with the session's `THE_LOOP_*` variables unset | 6781 passed, 22 failed (after the critic-review refinement); the same 22 fail on the unmodified code (`test_poll_status`, `test_poll_command`, `test_instances_cmd`, `test_lifecycle_cmd`, `test_critics`, `test_ask_reply_integration`). They read this machine's live daemon state and are unrelated to the change |
| Refinement after critic review: a claimed agent node parked on its own chain's wait is still re-evaluated on an event; a `code` node is not | `tests/test_graphlink.py`, `tests/test_graphlink_integration.py`, `tests/test_graph*.py` | 927 passed |
| Lint and format | `uv run ruff check cli hooks`, `uv run ruff format --check cli hooks`, `markdownlint-cli2` on the changed doc | pass |
| `graph complete` still claims an agent node | `the-loop graph complete issue-525` moved this item `implementation → verification` | pass |
