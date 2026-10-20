---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#507"
---

# Unit and fail-safe tests: answer a Slack mention in the thread it came from

T1 and T4 pass. T1 covers the delivery record, migration, `is_progress`, and critic C3's
malformed values. T4 covers a save failure, which degrades to a top-level post. Every
command ran from `cli/` on `21eb530` with `THE_LOOP_CLI_CONFIG` unset.

## T1 — `uv run python -m pytest -v tests/test_channels_reply_thread.py`

```text
tests/test_channels_reply_thread.py::test_the_delivery_record_keeps_the_reply_thread PASSED [  8%]
tests/test_channels_reply_thread.py::test_a_malformed_reply_thread_coerces_to_empty PASSED [ 16%]
tests/test_channels_reply_thread.py::test_migration_a_record_written_before_issue_507_has_no_reply_thread PASSED [ 25%]
tests/test_channels_reply_thread.py::test_is_progress[phase.progress-True] PASSED [ 33%]
tests/test_channels_reply_thread.py::test_is_progress[session.progress-True] PASSED [ 41%]
tests/test_channels_reply_thread.py::test_is_progress[review.progress-True] PASSED [ 50%]
tests/test_channels_reply_thread.py::test_is_progress[comment.agent-False] PASSED [ 58%]
tests/test_channels_reply_thread.py::test_is_progress[phase.started-False] PASSED [ 66%]
tests/test_channels_reply_thread.py::test_is_progress[phase-approval-pending-False] PASSED [ 75%]
tests/test_channels_reply_thread.py::test_a_truthy_malformed_reply_thread_coerces_to_empty[thread0-C0ROOM] PASSED [ 83%]
tests/test_channels_reply_thread.py::test_a_truthy_malformed_reply_thread_coerces_to_empty[not-a-ts-C0ROOM] PASSED [ 91%]
tests/test_channels_reply_thread.py::test_a_truthy_malformed_reply_thread_coerces_to_empty[1700.000100-channel2] PASSED [100%]
============================== 12 passed in 0.08s ==============================
```

## T4 — `uv run python -m pytest -v tests/test_channels_reply_thread_integration.py -k save_fails`

```text
tests/test_channels_reply_thread_integration.py::test_save_fails_the_reply_is_still_delivered_and_posts_top_level PASSED [100%]
======================= 1 passed, 12 deselected in 0.13s =======================
```

## The full suite

`uv run python -m pytest -q` (from `cli/`) on `265e84e`, the fix before the critic
round: `6480 passed, 2 warnings in 232.88s`. The two warnings are the existing
`test_runlock.py` fork deprecation warnings. On `21eb530`, after the critic fixes, the
full suite ran again as pre-commit's `pytest` hook and passed
([lint-and-typecheck.md](lint-and-typecheck.md)).
