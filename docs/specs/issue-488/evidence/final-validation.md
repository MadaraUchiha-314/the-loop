---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#488"
---

# Final validation: the explainer, the spec quiz and the code quiz

> The `evidence` node's proof, summarised from `testing-plan.md` § Verification results
> and mapped onto `requirements.md`. All tests named here are in `cli/tests/test_quiz.py`
> unless another file is named. The final run, after every review fix, was 6137 passed,
> with `make lint`, `make typecheck`, `make format-check` and `make validate` clean.

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| R1.1–1.2: one ticked `explainer` row, on by default | `test_the_row_is_ticked_and_absent_means_on`, `test_the_row_stands_for_the_four_nodes`, the checklist snapshots and the Jira checklist golden | [unit.md](unit.md) |
| R1.3–1.4: unticked means four declared skips under `explainer`; unreadable or absent means on | `test_unticking_the_row_declares_four_skips_under_its_token`, and the e2e `trivial-tier`, `ask-reply` and `review-rejection` scenarios, which untick the row | [unit.md](unit.md), [integration.md](integration.md) |
| R1.5: the confirmation states it | `test_leaving_the_row_alone_keeps_all_four_and_says_so` | [unit.md](unit.md) |
| R1.6: only `pdlc-work-item-loop` | `test_a_loop_without_the_skip_set_has_no_row`, plus `not-offered` for in-flight items (`test_frozen_graph_without_quiz_nodes_keeps_walking`) | [unit.md](unit.md) |
| R1.7: Slack carries the row | `test_the_slack_mirror_keeps_the_row_as_a_setting` | [unit.md](unit.md) |
| R2.1, R3.1, R3.6: the four nodes and their edges | e2e `happy-path` and `quiz-gates` walk them in order; `test_graph_model` pins the edges | [integration.md](integration.md) |
| R2.4, R3.6, R3.10: one comment with one box, on the ticket or on every open PR | `test_the_quiz_comment_links_the_page_and_carries_one_unticked_box`, `test_posting_is_idempotent_per_round_and_digest`, `test_the_code_quiz_goes_to_every_open_pull_request`, `test_the_code_quiz_falls_back_to_the_ticket_with_no_pull_request`, `test_a_comment_that_never_landed_is_posted_by_the_gate` | [unit.md](unit.md) |
| R2.5, R3.7: no exit while the box is unticked | `test_an_unticked_box_keeps_the_gate_waiting`, `test_a_tick_from_an_earlier_round_does_not_answer_this_one`, e2e `quiz-gates` | [unit.md](unit.md), [integration.md](integration.md) |
| R2.6, R3.8: a tick alone is noticed, attributed and advances | **live on GitHub (T11):** the edit history named the owner who ticked. Also `test_a_tick_by_an_authorized_user_passes_and_names_them`, the doorbell scenarios in `test_quiz_integration.py` (poller and webhook ring, a re-tick rings again, an unchanged tick rings once) | [live-attribution.md](live-attribution.md), [integration.md](integration.md) |
| R2.7: `micro` attests reading only | `test_a_micro_page_asks_the_author_to_attest_reading_only`, `test_the_read_only_line_does_not_answer_a_quiz_that_was_there`, `test_an_unfilled_depth_row_keeps_the_quiz_line` | [unit.md](unit.md) |
| R3.5: the node needs its record | `test_a_record_with_no_location_blocks_the_gate`; the `validate-artifacts` exit on `spec-explainer` and `code-explainer` | [unit.md](unit.md) |
| R3.9: the briefing links the explainer first | the "Start here" line in `templates/pr-briefing.md`, plus the PR-briefing Jira golden | [unit.md](unit.md) |
| R5.1–5.3: publishing by mode | the reference's publishing table (`skills/the-loop/reference/explainer.md`). This work item's own explainer was published as a Claude artifact (claude harness, `claudeArtifact` false) | the reviewer briefing on PR #489 |
| R5.4: a committed page gets a safe view command | `test_a_committed_page_gets_view_commands_built_only_from_safe_parts`, `test_a_hostile_location_gets_no_shell_command` | [unit.md](unit.md) |
| R5.5: specs stay the source of truth | no gate reads the page; the gates read the record's `Location`/`Depth` rows and the spec files only | design C1–C8; code review |
| R5.6: a spec change after publishing means a new page | `test_a_spec_changed_after_publishing_blocks_until_the_page_is_rebuilt` (at publish), `test_a_changed_spec_routes_back_as_stale` (after posting) | [unit.md](unit.md) |
| R6.6: offline feedback, revealed only after a choice | T5: 0 feedback before a choice, 0 network requests, 0 page errors, and no overflow at 375 px. T9: axe found 0 violations | [ui/check.md](ui/check.md), [ui/a11y.md](ui/a11y.md), [ui/quiz-flow.gif](ui/quiz-flow.gif) |
| R2.2–2.3, R3.2–3.4, R4, R6.1–6.5, R6.7: page content and quiz quality | judged in review, as the testing plan says. The rules are a checklist in the reference. This work item's own explainer and quiz were checked against them | the explainer artifact; PR #489 review |
| Abuse cases 1–6 | one or more negative tests each; see the security review's checklist item 7 | [security-review.md](security-review.md) |

**Open at this point:**

- The tier-4 security sign-off and the SR1 decision are with @MadaraUchiha-314.
- The page-content criteria are judged by the human reviewer.
