# Abuse-case tests (T8)

Run on 2026-11-20 at `a0b978dd`, after the review fixes, from `cli/`, with `THE_LOOP_CLI_CONFIG`,
`THE_LOOP_INSTANCE` and `THE_LOOP_WORK_ITEM` unset. A daemon-spawned session exports
those, and with them set some unrelated status tests read the live daemon.

| Row | Command | Result |
|---|---|---|
| T8 | `uv run python -m pytest -q -k "abuse or unauthorized or foreign_work_item or nudge_is_fixed"` | 324 passed, 7606 deselected in 11.92s |

The expression also selects older tests of other work items. The tests that prove
this work item's abuse cases:

| Abuse case | Tests | File |
|---|---|---|
| 1. Unauthorized reply to an ask with a default | `test_abuse_an_unauthorized_reply_does_not_stop_the_default` | `test_ask_deadline_integration.py` |
| 2. Refused comments on a stalled item | `test_abuse_unauthorized_comments_do_not_stop_the_nudges_or_the_notice` | `test_watchdog_integration.py` |
| 3. A default steered into an approval | `test_abuse_a_default_of_approved_taken_next_to_a_human_gate_answers_nothing`, `test_abuse_the_agents_own_marked_comment_is_no_answer` | `test_ask_deadline_integration.py` |
| | `test_abuse_a_default_of_approved_answers_no_human_gate` | `test_channels_sessionnotes.py` |
| | `test_abuse_a_wait_cannot_put_a_clock_on_a_human_gate` | `test_stop_check.py` |
| 4. Endless declared waits | `test_abuse_endless_declared_waits_are_refused` | `test_stop_check.py` |
| 5. Token burn on a stuck session, across restarts | `test_abuse_a_session_that_answers_every_nudge_with_an_empty_turn` | `test_watchdog_integration.py` |
| 6. Markup in a default | `test_abuse_a_default_with_markup_is_quoted_as_words_on_github` | `test_ask_deadline_integration.py` |
| | `test_abuse_a_default_with_markup_is_inert_in_the_github_comment`, `test_abuse_a_default_with_markup_is_inert_in_slack` | `test_channels_sessionnotes.py` |
| | `test_abuse_a_default_with_markup_and_mentions_renders_inert` | `test_channels_shortform.py` |
| 6. Markup in a wait's condition | `test_abuse_a_condition_with_markup_is_one_line_of_words_on_every_surface` | `test_stop_check.py` |
| 7. A Stop gate that never lets go | `test_abuse_a_service_refusing_forever_is_capped_and_the_give_up_reported` | `test_harness_gate.py` |
| A hook verb naming another work item | `test_a_foreign_work_item_is_refused_and_nothing_is_recorded`, `test_the_route_answers_404_for_a_foreign_work_item`, `test_the_verb_refuses_a_foreign_work_item_before_any_call`, `test_turn_start_for_a_foreign_work_item_records_nothing`, `test_a_declared_wait_for_a_foreign_work_item_records_nothing` | `test_stop_check.py` |
| The nudge carries no untrusted text | `test_nudge_is_fixed_and_carries_no_untrusted_text` | `test_watchdog.py` |
| A daemon session that names no work item | `test_the_verbs_refuse_a_daemon_session_that_names_no_work_item` | `test_stop_check.py` |
| A blanked pointer file (security review F1) | `test_abuse_a_session_whose_state_file_is_gone_is_told_to_a_person_once` | `test_watchdog.py` |
| A reply nobody vouched for (F4) | `test_abuse_a_reply_nobody_vouched_for_closes_asks_and_resets_nothing` | `test_session_state.py` |
| Control characters in a default (F3) | `test_abuse_a_default_with_control_characters_is_recorded_without_them`, `test_abuse_a_default_recorded_with_control_characters_is_pasted_without_them` | `test_ask_deadline_integration.py`, `test_watchdog.py` |
| An input-only collaborator's comment (F5) | `test_abuse_a_collaborators_comment_answers_no_ask_and_resets_no_budget` | `test_dispatch_ask_answers.py` |
| A second timed ask on one step | `test_abuse_a_second_default_on_the_same_step_is_refused` | `test_ask_deadline_integration.py` |

## What these tests do not prove

The service authenticates no caller. "Foreign work item" is refused when the ref
names no live registered session, and by the CLI when the ref differs from
`THE_LOOP_WORK_ITEM`. A session that unsets its daemon variables, or calls the API directly, can
still name another registered work item. See `security-review.md`.
