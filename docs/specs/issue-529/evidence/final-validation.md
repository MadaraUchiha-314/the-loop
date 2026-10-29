---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#529"
---

# Final validation: a Slack kickoff offers Do or Start

> The `evidence` node's proof: each acceptance criterion of `requirements.md`, mapped to
> how the executed `testing-plan.md` proved it. Summarised from the plan's Verification
> results. Raw output sits beside this file.

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| R1.1: the "Opened" reply carries Do then Start in one actions block | T1 `test_reply_blocks_offer_do_then_start_each_described`, `test_kickoff_commands_are_do_then_start`; T2 the Do-press scenario asserts `[command:do, command:start]` on a real kickoff | [unit.md](unit.md), [integration.md](integration.md) |
| R1.2: one fixed line per rendered button | T1 asserts the exact `*Do* — …\n*Start* — …` section; T2 asserts both lines on the kickoff reply; T5 shows it rendered | [unit.md](unit.md), [integration.md](integration.md), [ui-visual.md](ui-visual.md) |
| R1.3: every kickoff path renders the same | T2 kickoff message, picker answer (`test_a_picker_answers_reply_offers_do_and_start`) and `/the-loop new` (`test_new_opens_the_work_item_and_its_thread`) | [integration.md](integration.md) |
| R1.4: a disabled keyword or a missing grant withholds its button | T2 `test_a_disabled_do_keyword_leaves_start_alone`, `test_a_kickoff_without_the_command_grant_offers_no_loop`; T1 empty-commands case | [unit.md](unit.md), [integration.md](integration.md) |
| R1.5: each value is the configured keyword | T1 asserts `the-loop do` / `the-loop start` as values | [unit.md](unit.md) |
| R2.1: Do arms the ad-hoc loop | T2: the press records an unmarked `the-loop do` on the new issue, `parse_command` reads `do`, and `LOOP_FOR_CONTROL_COMMAND["do"] == pdlc-adhoc-loop`; T12 re-runs the existing `-k adhoc` tests (64 passed) | [integration.md](integration.md) |
| R2.2: Start is unchanged | T2 the issue-337 Start-press test, updated only for the button's index | [integration.md](integration.md) |
| R2.3: a landed press removes both buttons and names the one pressed | T2: the edit has no buttons and starts `✅ *Do*` | [integration.md](integration.md) |
| R2.4: a press that does not land keeps the buttons | unchanged `report_press` rule, covered by the issue-337 suite under T12 | [regression.md](regression.md) |
| R2.5: typed keywords still work | T12 the whole suite (6803 passed) | [regression.md](regression.md) |
| Abuse cases 1, 2, 4 | T8 negative tests | [integration.md](integration.md), [security-review.md](security-review.md) |
| NFR: no new config, grant, scope or schema | the diff: no schema or config file touched | [security-review.md](security-review.md) |

T4 and T11 are not covered here. The plan marks them `n/a`, with the reason, because
they would need a live Slack workspace. Pressing Do in a real workspace is offered to
the author as an optional post-merge check.
