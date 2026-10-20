---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#507"
---

# Integration tests: answer a Slack mention in the thread it came from

The regression test is red on `origin/main` and green on this branch. The integration
file runs the real `SlackBotChannel` and the real inbound pipeline against
`FakeSlackClient`. Every command ran from `cli/` with `THE_LOOP_CLI_CONFIG` unset.

## Red on `origin/main` (T2.1)

`cli/the_loop/channels/{slack,inbound,state,room_policy}.py` were checked out from
`origin/main`, with the new test file kept, then restored. The 5 failures are the
scenarios that need the fix. Each fails because the answer is posted with
`thread_ts=None`. The 7 that pass are the behaviours the fix must not change.

```text
FAILED tests/test_channels_reply_thread_integration.py::test_the_answer_to_a_thread_mention_is_a_reply_in_that_thread
FAILED tests/test_channels_reply_thread_integration.py::test_every_answer_stays_in_the_thread_until_something_else_happens
FAILED tests/test_channels_reply_thread_integration.py::test_a_mention_in_another_thread_moves_the_answer_there
FAILED tests/test_channels_reply_thread_integration.py::test_progress_does_not_end_the_reply_thread
FAILED tests/test_channels_reply_thread_integration.py::test_abuse_an_unauthorized_thread_mention_sets_no_reply_thread
5 failed, 7 passed in 0.27s
```

## T2 — `uv run python -m pytest -v tests/test_channels_reply_thread_integration.py`

```text
tests/test_channels_reply_thread_integration.py::test_the_answer_to_a_thread_mention_is_a_reply_in_that_thread PASSED [  8%]
tests/test_channels_reply_thread_integration.py::test_every_answer_stays_in_the_thread_until_something_else_happens PASSED [ 16%]
tests/test_channels_reply_thread_integration.py::test_a_mention_in_another_thread_moves_the_answer_there PASSED [ 25%]
tests/test_channels_reply_thread_integration.py::test_a_top_level_mention_is_answered_at_the_top_level PASSED [ 33%]
tests/test_channels_reply_thread_integration.py::test_a_phase_change_ends_the_reply_thread PASSED [ 41%]
tests/test_channels_reply_thread_integration.py::test_a_gate_prompt_ends_the_reply_thread PASSED [ 50%]
tests/test_channels_reply_thread_integration.py::test_progress_does_not_end_the_reply_thread PASSED [ 58%]
tests/test_channels_reply_thread_integration.py::test_room_policy_still_drops_what_it_drops PASSED [ 66%]
tests/test_channels_reply_thread_integration.py::test_without_a_mention_the_answer_is_top_level_as_before PASSED [ 75%]
tests/test_channels_reply_thread_integration.py::test_abuse_an_unauthorized_thread_mention_sets_no_reply_thread PASSED [ 83%]
tests/test_channels_reply_thread_integration.py::test_abuse_a_reply_thread_in_another_channel_is_ignored PASSED [ 91%]
tests/test_channels_reply_thread_integration.py::test_save_fails_the_reply_is_still_delivered_and_posts_top_level PASSED [100%]
============================== 12 passed in 0.18s ==============================
```

## T3 — `… tests/test_channels_reply_thread_integration.py -k abuse`

```text
tests/test_channels_reply_thread_integration.py::test_abuse_an_unauthorized_thread_mention_sets_no_reply_thread PASSED [ 50%]
tests/test_channels_reply_thread_integration.py::test_abuse_a_reply_thread_in_another_channel_is_ignored PASSED [100%]
======================= 2 passed, 10 deselected in 0.10s =======================
```

## Scenarios — `the-loop scenarios --root . --glob 'cli/tests/test_channels_reply_thread_integration.py' --format markdown`

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 1 | the agent answers where it was asked | a collaborator mentions the-loop inside a thread of the room | docs/specs/issue-507/bugfix.md R1.1, R1.2, R1.4, R3.3 | cli/tests/test_channels_reply_thread_integration.py:71 |
| 2 | the agent answers where it was asked | after a thread mention, someone mentions the-loop at the top level | docs/specs/issue-507/bugfix.md R2.2 | cli/tests/test_channels_reply_thread_integration.py:118 |
| 3 | the agent answers where it was asked | the work item moves to a new phase after a thread mention | docs/specs/issue-507/bugfix.md R2.3 | cli/tests/test_channels_reply_thread_integration.py:138 |
| 4 | only an authorized speaker steers the answer | a stranger mentions the-loop in a room thread | docs/specs/issue-507/bugfix.md abuse case 1 | cli/tests/test_channels_reply_thread_integration.py:225 |
