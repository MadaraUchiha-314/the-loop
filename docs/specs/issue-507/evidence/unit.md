---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#507"
---

# Unit and fail-safe tests: answer a Slack mention in the thread it came from

T1 (the delivery record, migration, `is_progress`) and T4 (a save failure degrades to a
top-level post) pass. Every command ran from `cli/` with `THE_LOOP_CLI_CONFIG` unset.

## T1 — `uv run python -m pytest -v tests/test_channels_reply_thread.py`

```text
tests/test_channels_reply_thread.py::test_the_delivery_record_keeps_the_reply_thread PASSED [ 11%]
tests/test_channels_reply_thread.py::test_a_malformed_reply_thread_coerces_to_empty PASSED [ 22%]
tests/test_channels_reply_thread.py::test_migration_a_record_written_before_issue_507_has_no_reply_thread PASSED [ 33%]
tests/test_channels_reply_thread.py::test_is_progress[phase.progress-True] PASSED [ 44%]
tests/test_channels_reply_thread.py::test_is_progress[session.progress-True] PASSED [ 55%]
tests/test_channels_reply_thread.py::test_is_progress[review.progress-True] PASSED [ 66%]
tests/test_channels_reply_thread.py::test_is_progress[comment.agent-False] PASSED [ 77%]
tests/test_channels_reply_thread.py::test_is_progress[phase.started-False] PASSED [ 88%]
tests/test_channels_reply_thread.py::test_is_progress[phase-approval-pending-False] PASSED [100%]
============================== 9 passed in 0.06s ===============================
```

## T4 — `uv run python -m pytest -v tests/test_channels_reply_thread_integration.py -k save_fails`

```text
tests/test_channels_reply_thread_integration.py::test_save_fails_the_reply_is_still_delivered_and_posts_top_level PASSED [100%]
======================= 1 passed, 11 deselected in 0.43s =======================
```

## The full suite

`uv run python -m pytest -q` (from `cli/`), after the fix: `6480 passed, 2 warnings in
232.88s`. The two warnings are the existing `test_runlock.py` fork deprecation warnings.
