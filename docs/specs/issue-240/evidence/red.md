# Evidence — the red run (issue-240)

Every new assertion, run against **unfixed** code, before any production change was
written (`tdd.mode: standard`). Committed as its own commit so the red→green transition is
in the history rather than only in this file.

Testing plan rows: T2, T3, T4, T5, T6 · Requirements: R4.1, R4.2, R4.3

## `cli/tests/test_poller.py` — collection fails, because the function does not exist

```console
$ uv run --project cli python -m pytest -q cli/tests/test_poller.py
==================================== ERRORS ====================================
____________________ ERROR collecting tests/test_poller.py _____________________
ImportError while importing test module '/home/user/the-loop/cli/tests/test_poller.py'.
Traceback:
cli/tests/test_poller.py:51: in <module>
    from the_loop.poller.poller import (  # noqa: F401 (PollSummary re-exported too)
E   ImportError: cannot import name 'giveup_notice' from 'the_loop.poller.poller'
=========================== short test summary info ============================
ERROR cli/tests/test_poller.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.57s
```

That module is excluded from the run below so the other three can be observed failing on
their **assertions** rather than on a collection error.

## The other three modules — four failing assertions

```console
$ uv run --project cli python -m pytest -q \
    cli/tests/test_tmux_runner.py \
    cli/tests/test_tmux_runner_integration.py \
    cli/tests/test_poller_integration.py
E       AssertionError: assert ['has-session..., 'send-keys'] == ['has-session...paste-buffer']
E
E         At index 4 diff: 'send-keys' != 'load-buffer'
E         Right contains one more item: 'paste-buffer'
E         Use -v to get more diff
E       AssertionError: assert 1 == 2
E        +  where 1 = len(['/tmp/the-loop-evt-z8fnz7c2'])
E       AssertionError: assert ['has-session..., 'send-keys'] == ['has-session...paste-buffer']
E
E         At index 4 diff: 'send-keys' != 'load-buffer'
E         Right contains one more item: 'paste-buffer'
E         Use -v to get more diff
E       TypeError: Poller.__init__() got an unexpected keyword argument 'comment_runner'
FAILED cli/tests/test_tmux_runner.py::TestTmuxRunner::test_deliver_pastes_bracketed_then_submits_without_send_keys
FAILED cli/tests/test_tmux_runner.py::TestTmuxRunner::test_deliver_removes_both_temporary_files
FAILED cli/tests/test_tmux_runner_integration.py::test_followup_event_is_pasted_into_the_running_session
FAILED cli/tests/test_poller_integration.py::test_an_abandoned_comment_is_reported_on_the_work_item
4 failed, 146 passed in 4.92s
```

## What each failure is asserting

| Failure | The behaviour it demands |
|---|---|
| `test_deliver_pastes_bracketed_then_submits_without_send_keys` | The delivery issues four commands and none of them is `send-keys` — the argv contract R4.2 asks for, so a client-resolved command coming back fails on any tmux rather than only on ≥ 3.7 with an observer attached. |
| `test_deliver_removes_both_temporary_files` | Two tempfiles are written (prompt, submit) and both are unlinked, including when the second paste fails. Today there is one. |
| `test_followup_event_is_pasted_into_the_running_session` | The same contract through the real webhook→dispatch→tmux pipeline. |
| `test_an_abandoned_comment_is_reported_on_the_work_item` | The poller can be handed a `gh` runner at all — the first thing missing on the way to posting a give-up notice. |
| `test_poller.py` collection | `giveup_notice` exists as a module-level function. |
