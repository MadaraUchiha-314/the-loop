---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#449"
status: in-review            # draft | in-review | approved — locked with design.md
approvedBy: []
overrides: {}
riskTier: 4
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: Codex CLI as a hosting harness and critic

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md).
> Recorded retroactively during the PR #450 review; in review, not approved.
> Tests live in `cli/tests/test_codex_support.py` unless noted.

## What "proved" means here

- A Codex session resumes only its own conversation, and only inside the session store.
- Nothing the-loop writes for Codex reaches the project's history or widens trust.
- An operator's configuration is migrated without changing what the-loop offers.

## Test matrix

| ID | Requirement | Proof |
| --- | --- | --- |
| T1 | R2.1, R2.2 | `test_resume_uses_the_launch_marker_even_after_an_operator_starts_a_new_chat` |
| T2 | R2.3 | `test_rollout_lookup_rejects_unsafe_or_unknown_id`, `test_rollout_lookup_requires_explicit_absolute_directory_metadata`, `test_rollout_lookup_refuses_a_wrong_cwd_ambiguous_marker_and_escaping_symlink` |
| T3 | R2.4 | `test_a_resolved_rollout_is_not_searched_for_again` |
| T4 | R3.1 | `test_instruction_setup_preserves_operator_text_and_hook_choices`, `test_native_override_instructions_are_used_without_changing_other_file`, `test_instruction_setup_rejects_an_escaping_symlink` |
| T5 | R3.2 | `test_spawn_setup_keeps_untracked_instructions_out_of_git`, `test_spawn_setup_reports_a_tracked_instructions_file` |
| T6 | R3.3 | `test_spawn_setup_uses_one_user_hook_definition_across_worktrees`, `test_a_stale_gate_from_another_install_is_replaced_not_duplicated` |
| T7 | R3.4 | `test_parallel_codex_trust_writes_preserve_every_project`, `test_a_worktree_main_root_at_home_is_never_trusted` |
| T8 | R3.5 | `test_codex_home_is_stripped_and_expanded_for_every_writer` |
| T9 | R4.1 | `test_deprecated_harness_arguments_*`, `test_malformed_deprecated_harness_arguments_are_dropped_once` |
| T10 | R4.2, R4.3 | `test_codex_mcp_delegation_uses_codex_and_reads_its_final_json` |
| T11 | R5.1 | `test_the_default_skips_a_default_true_that_cannot_host` (`test_dispatcher_harness.py`) |
| T12 | R5.2 | `test_missing_arming_labels_are_observable_without_widening_the_gate` |
| T13 | R5.3 | `test_disconnected_graphql_retries_a_read_once_but_never_a_write` |
| T14 | R1.3 | Codex JSONL critic output and usage tests in `test_codex_support.py` |
| T15 | R1.1, R1.2 | Manual end-to-end run on `the-loop-testing` with a real Codex binary, recorded in `evidence/` (pending) |

## Not automated

T15 needs an authenticated Codex CLI. The hook-trust step (`/hooks`) is interactive by
Codex's design and is verified by hand.
