---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#536"
---

# Final validation: publish a work item's spec chain as one Claude doc

> Summarised from [`testing-plan.md`](../testing-plan.md) § Verification results and
> [`verification.md`](verification.md), run at `23efe118`. Later commits changed only
> skill text and evidence records.

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| R1.1 doc row ticked, artifact unticked | `test_the_checklist_offers_the_doc_row_ticked_by_default`, `test_an_untouched_checklist_freezes_the_owners_defaults` | [verification.md](verification.md) T1–T6 |
| R1.2 section note | the same render test (at most one, both ticked uses the default); `test_no_fact_the_comment_stated_is_lost` | T1, T8 |
| R1.3 handoff with a spec artifact keeps the artifact ticked | `test_a_named_spec_artifact_ticks_the_claude_artifact_row_instead_of_the_doc`, `test_a_handoff_with_no_spec_artifact_keeps_the_doc_default` | T1 |
| R1.4 absent on a contribution | `test_a_contribution_is_not_offered_the_doc_row` | T1 |
| R1.5 never a phase | `test_the_doc_row_is_never_read_as_a_phase` | T2 |
| R1.6 Slack mirror | `test_selection_control.py` pin | T7 |
| R2.1–R2.2 doc on `claude` or an unknown harness | `test_the_doc_ticked_alone_on_claude_publishes_a_doc`, `test_the_doc_with_no_known_harness_is_applied` | T2 |
| R2.3 both ticked → the default | `test_both_ticked_uses_the_default_doc`, `test_both_ticked_after_an_artifact_handoff_uses_the_artifact`, `test_both_ticked_on_another_harness_is_not_applied`, `test_the_default_follows_the_handoff` | T2 (re-verification) |
| R2.4 another harness → not applied | `test_the_doc_on_another_harness_is_not_applied` | T2 |
| R2.5 unticked/absent → false | `test_unticked_or_absent_is_not_a_doc` | T2 |
| R2.6 confirmation in every direction | the assertions on the confirmation text in each R2 test | T2 |
| R2.7 never both true | the both-ticked tests + `test_both_true_on_disk_keeps_the_artifact` | T2, T3 |
| R3.1 frozen in state, decision, graph | `test_the_doc_ticked_alone_on_claude_publishes_a_doc` (decision + graph keys) | T4 |
| R3.2 boolean only; written only when true | `test_anything_but_the_boolean_true_reads_as_false`, `test_a_legacy_state_saves_byte_identical` | T3 |
| R3.3 both true on disk | `test_both_true_on_disk_keeps_the_artifact` | T3 |
| R3.4 archive | `test_the_archive_records_and_summarises_the_doc` | T6 |
| R3.5 state doc | `test_the_attribute_table_is_documented` (in `make check`) | T8 |
| R4.1–R4.2 prompt line | `test_the_outer_loop_prompt_tells_the_session_to_publish_a_doc`, `test_no_other_prompt_carries_the_doc_line`, `test_the_prompt_reads_the_frozen_state` | T5 |
| R4.3–R4.7 skill procedure | review of the skill text | [self-review.md](self-review.md), [critic-review.md](critic-review.md) |
| R4.8 capability docs | the docs listed in [documentation.md](documentation.md) | — |
| R5.1–R5.3 `spec-doc` in the record | `test_a_record_naming_a_spec_doc_round_trips`, `test_a_spec_doc_that_is_not_an_https_link_is_rejected`, `test_a_spec_doc_beside_a_spec_artifact_is_rejected` | T13 |
| R5.4–R5.5 adopted and named | `test_an_imported_spec_chain_doc_url_is_recorded_and_rendered`, `test_a_record_doc_url_that_is_not_claude_ai_is_not_adopted`, `test_a_doc_url_that_is_not_https_is_not_rendered`, `test_a_named_spec_doc_keeps_the_doc_row_ticked` | T13 |
| R5.6 archive, skill, docs | the archive test; [documentation.md](documentation.md) | T13 |
| Abuse cases | negative tests, plus the checklist review | [security-review.md](security-review.md) |
| Regression | `make check`: 6914 passed after the handoff doc import; ruff, pyright, validation and pre-commit clean | T8 |
