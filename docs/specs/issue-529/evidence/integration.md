---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#529"
---

# Integration scenarios (T2) and abuse cases (T8)

## `uv run python -m pytest -q tests/test_channels_integration.py tests/test_channels_commands.py tests/test_channels_kickoff_picker.py`

```text
173 passed in 2.18s
```

Red → green: before task 2's code, four failed, all on a reply carrying
`['the-loop start']` where `['the-loop do', 'the-loop start']` was expected. The four
were the kickoff, `/the-loop new`, the picker, and the Do press.

## The issue-529 scenarios and abuse cases, verbose

```text
tests/test_channels_integration.py::test_a_kickoff_reply_offers_do_and_pressing_it_records_the_do_keyword PASSED
tests/test_channels_integration.py::test_a_disabled_do_keyword_leaves_start_alone PASSED
tests/test_channels_integration.py::test_a_kickoff_without_the_command_grant_offers_no_loop PASSED
tests/test_channels_integration.py::test_an_unlisted_members_do_press_arms_nothing PASSED
tests/test_channels_integration.py::test_a_crafted_do_press_value_arms_nothing PASSED
tests/test_channels_buttons.py::test_reply_blocks_offer_do_then_start_each_described PASSED
tests/test_channels_buttons.py::test_kickoff_commands_are_do_then_start PASSED
tests/test_channels_buttons.py::test_a_command_without_a_description_renders_no_line PASSED
tests/test_channels_kickoff_picker.py::test_a_picker_answers_reply_offers_do_and_start PASSED
====================== 9 passed, 120 deselected in 0.32s =======================
```

| Test | Proves |
|------|--------|
| `test_a_kickoff_reply_offers_do_and_pressing_it_records_the_do_keyword` | R1.1, R1.2, R2.1, R2.3: Do then Start, each described. A Do press records an unmarked `the-loop do`, which maps to `pdlc-adhoc-loop`, and the reply is edited with "Do" and no buttons |
| `test_a_picker_answers_reply_offers_do_and_start` | R1.3: the picker path |
| `test_new_opens_the_work_item_and_its_thread` (updated) | R1.3: `/the-loop new` |
| `test_a_disabled_do_keyword_leaves_start_alone` | R1.4 |
| `test_a_kickoff_without_the_command_grant_offers_no_loop` | R1.4, abuse 4 |
| `test_an_unlisted_members_do_press_arms_nothing` | abuse 1 |
| `test_a_crafted_do_press_value_arms_nothing` | abuse 2 |
| `test_a_kickoff_reply_carries_start_and_its_press_records_the_keyword` (updated) | R2.2: Start is unchanged |

## The ad-hoc loop's existing tests (`-k adhoc`)

```text
64 passed, 6739 deselected in 2.89s
```
