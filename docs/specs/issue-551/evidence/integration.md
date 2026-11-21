# Integration scenarios (T2, T9)

Run on 2026-11-20 at `a0b978dd`, after the review fixes, from `cli/`, with `THE_LOOP_CLI_CONFIG`,
`THE_LOOP_INSTANCE` and `THE_LOOP_WORK_ITEM` unset. A daemon-spawned session exports
those, and with them set some unrelated status tests read the live daemon.

| Row | Command | Result |
|---|---|---|
| T2 | `uv run python -m pytest -q tests/test_watchdog_integration.py tests/test_ask_deadline_integration.py tests/test_inbound_readonly_integration.py tests/test_gate_pointer_integration.py` | 55 passed in 5.75s |
| T2 | `uv run the-loop scenarios --root "$PWD" --glob 'cli/tests/test_*_integration.py' --format markdown` | 889 lines; every scenario title of the testing plan's trace appears |
| T9 | within the whole suite: `tests/test_channels_sessionnotes.py` asserts each new Slack message's `text` fallback is its short form and names the state in words | passed |

## This work item's scenarios, from the scenario table

| Scenario | Requirement | Location |
|---|---|---|
| the ask is recorded with its default and its deadline | #R6.1 | `cli/tests/test_ask_deadline_integration.py:162` |
| each ask has its own id | #R6.1 | `cli/tests/test_ask_deadline_integration.py:193` |
| the question on GitHub and in Slack states the default and the time | #R6.1 | `cli/tests/test_ask_deadline_integration.py:210` |
| a default with no wait is never taken by itself | #R6.1 | `cli/tests/test_ask_deadline_integration.py:255` |
| a wait is given without a default answer | #R6.6 | `cli/tests/test_ask_deadline_integration.py:272` |
| the requested wait is shorter than the operator's minimum | #R6.5 | `cli/tests/test_ask_deadline_integration.py:293` |
| the command's output after an ask with a deadline, and without one | #R6.9 | `cli/tests/test_ask_deadline_integration.py:318` |
| a default answer longer than 600 characters | docs/specs/issue-551/design.md § Security design | `cli/tests/test_ask_deadline_integration.py:342` |
| an answer cancels the default | #R6.3 | `cli/tests/test_ask_deadline_integration.py:356` |
| a comment arrives when nothing was asked | #R6.3 | `cli/tests/test_ask_deadline_integration.py:389` |
| a user who is not authorized replies to an ask that has a default | #security-considerations (abuse case 1) | `cli/tests/test_ask_deadline_integration.py:410` |
| the question's own comment comes back as an event | docs/specs/issue-551/design.md § Security design | `cli/tests/test_ask_deadline_integration.py:454` |
| the text of a default answer contains markup and mentions | #security-considerations (abuse case 6) | `cli/tests/test_ask_deadline_integration.py:475` |
| the text of a default answer contains control characters | #security-considerations | `cli/tests/test_ask_deadline_integration.py:514` |
| a default is taken at its deadline, once, across a restart | #R6.2 R6.10 | `cli/tests/test_ask_deadline_integration.py:571` |
| an answer after the default still reaches the session | #R6.4 | `cli/tests/test_ask_deadline_integration.py:627` |
| a question with no default is reminded once | #R6.7 R6.10 | `cli/tests/test_ask_deadline_integration.py:666` |
| a session states "approved" as its default and lets the deadline pass | #security-considerations (abuse case 3), R6.8 | `cli/tests/test_ask_deadline_integration.py:709` |
| the question could not be posted anywhere | #R6.2 | `cli/tests/test_ask_deadline_integration.py:766` |
| the requested wait is longer than the-loop accepts | #R6.6 | `cli/tests/test_ask_deadline_integration.py:800` |
| the command is given a default answer longer than 600 characters | docs/specs/issue-551/design.md § Security design | `cli/tests/test_ask_deadline_integration.py:831` |
| a session asks again with a wait after its default was taken | #security-considerations | `cli/tests/test_ask_deadline_integration.py:857` |
| a session queues a second deadline before the first one passes | #security-considerations | `cli/tests/test_ask_deadline_integration.py:893` |
| a caller adds the mark of an authorized reply to its request |  § Security considerations | `cli/tests/test_ask_reply_integration.py:128` |
| a claim returns the next assignment and says to continue | #R1.1 | `cli/tests/test_claim_assignment_integration.py:79` |
| an advance the daemon drives delivers the assignment once | #R1.5 | `cli/tests/test_claim_assignment_integration.py:110` |
| a stop with work owed is refused past an approved gate |  R3.1, R3.3, R3.5 | `cli/tests/test_gate_pointer_integration.py:267` |
| a stop with an open ask is allowed |  R3.2, R3.8 | `cli/tests/test_gate_pointer_integration.py:298` |
| the gate gives up after its attempts and records why |  R3.6, R3.8 | `cli/tests/test_gate_pointer_integration.py:337` |
| a comment does not block an agent node | #R5.1 | `cli/tests/test_inbound_readonly_integration.py:121` |
| a met exit gate still advances on a comment | #R5.2 | `cli/tests/test_inbound_readonly_integration.py:152` |
| a human gate still classifies the comment it receives | #R5.3 | `cli/tests/test_inbound_readonly_integration.py:174` |
| a human gate still waits on a comment that is not an answer | #R5.3 | `cli/tests/test_inbound_readonly_integration.py:196` |
| a session's own failing claim is still recorded, and a repeat escalates | #R5.4 | `cli/tests/test_inbound_readonly_integration.py:221` |
| a comment does not block an agent node of a pull request's inner loop | #R5.1 | `cli/tests/test_inbound_readonly_integration.py:259` |
| a session asks, waits, and reports its turns through a manager |  R2.1, R5.1, R6.1; | `cli/tests/test_manager_integration.py:479` |
| an idle session is nudged, then a person is told once | #R4.1 R4.2 R4.3 R4.4 | `cli/tests/test_watchdog_integration.py:109` |
| a restart repeats no nudge and no notice | #R4.10 | `cli/tests/test_watchdog_integration.py:167` |
| a stall ends when the session takes a turn, and the notice is edited | #R4.5 R4.9 R7.5 | `cli/tests/test_watchdog_integration.py:202` |
| a switched-off watchdog sends nothing and the gate still holds | #R4.12 | `cli/tests/test_watchdog_integration.py:273` |
| the stall notice is a short form in the work item's conversation | #R7.4 R4.4 | `cli/tests/test_watchdog_integration.py:317` |
| the watcher runs with the service, whichever ingress is enabled | #R4.11 | `cli/tests/test_watchdog_integration.py:367` |
| a stuck session cannot spend tokens without end | #security-considerations (abuse case 5) | `cli/tests/test_watchdog_integration.py:411` |
| a user who is not authorized comments repeatedly on a stalled work item | #security-considerations (abuse case 2) | `cli/tests/test_watchdog_integration.py:444` |
