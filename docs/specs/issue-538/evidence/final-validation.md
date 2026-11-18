---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#538"
---

# Final validation: tell the work item's session what happens to its pull-request sessions

> Summarised from [`testing-plan.md`](../testing-plan.md) § Verification results and
> [`verification.md`](verification.md). After the review fixes (self-review F1, critic
> C1–C2), the affected suites were re-run at `fbed45c`:
> `pytest tests/test_prnotice.py tests/test_pr_notices_integration.py tests/test_outer_reevaluation_integration.py tests/test_tmux_runner.py tests/test_webhook_routing_integration.py tests/test_graph_loops.py tests/test_graph_multirepo_integration.py`
> → **299 passed**. Ruff, ruff format and pyright are clean at the same commit.

## Final validation evidence

| Acceptance criterion | How it was proved |
|----------------------|-------------------|
| R1.1 `spawned` | `test_a_spawned_pull_request_session_is_reported` |
| R1.2 `declined` (five reasons) | `test_a_declined_pull_request_session_rides_with_the_event` (no-separate-checkout) drives the path end to end; every reason code renders its fixed phrase (`test_every_transition_…`, `test_a_known_decline_reason_…`). The `harness-unavailable`, `workspace-failed`, `shared-worktree` and `hook-refused` call sites pass a literal code through the same `_decline_into`. |
| R1.3 `spawn-failed` | `test_a_failed_spawn_rides_with_the_event` |
| R1.4 one paste with the event | the declined and spawn-failed scenarios assert one paste with the notice ahead of the event |
| R1.5 `merged` / `completed` | `test_a_merged_pull_request_session_is_reported_to_the_work_item`, `test_an_approved_inner_loop_is_reported_and_the_outer_gate_rerun`; the updated issue-172 scenario |
| R1.6 `closed` names the gate | `test_a_pull_request_closed_unmerged_is_reported_with_its_gate`, `test_a_closed_notice_says_whether_the_gate_keeps_waiting`, `test_inner_loop_gate_reports_…` |
| R1.7 `escalated` | `test_an_escalated_inner_loop_is_reported` |
| R1.8 `respawned` / `respawn-failed` | `test_a_respawned_…`, `test_a_failed_respawn_…`, `test_a_respawn_blocked_by_a_dead_occupant_…`, `test_the_work_items_own_respawn_sends_no_notice` |
| R1.9 one event per notice | every notice scenario asserts exactly one `session.pr_notice_*` |
| R2.1, R2.4 re-evaluate on merge; pass delivers the next assignment | `test_a_merge_releases_a_work_item_parked_on_its_inner_loops` (shipped graph, `implementation` → `verification`, assignment delivered) |
| R2.2 re-evaluate on inner `complete` | `test_an_approved_inner_loop_is_reported_and_the_outer_gate_rerun` |
| R2.3 only when parked on an `await-inner-loops` node | `test_an_unparked_work_item_is_left_untouched`, `test_a_node_without_the_inner_loop_gate_is_left_untouched`, `test_waits_on_inner_loops_…` |
| R2.5 wait recorded, no retry | `test_a_second_pending_inner_loop_keeps_the_work_item_waiting` |
| R2.6 no re-evaluation on close-unmerged | `test_a_pull_request_closed_unmerged_is_reported_with_its_gate` |
| R3.1–R3.3 paused / absent / paste failure | `test_a_paused_work_item_…`, `test_a_work_item_with_no_session_to_tell_…`, `test_a_failed_paste_is_recorded_and_not_retried` |
| R3.4 inner state as today | the close-path scenarios still close the endpoint; `on_pr_close` / `on_pr_state` are unchanged |
| R3.5 re-evaluation fault contained; never holds the webhook | `test_a_raising_runtime_is_contained`, `test_a_slow_outer_reevaluation_does_not_hold_the_webhook` |
| R4.1–R4.2 one-way rule | the byte-identical state assertion; the re-run goes only through `Runtime.advance` |
| R4.3 never posted to a thread | no notice path calls a GitHub client; the suite's autouse fixture fails any GitHub call |
| Abuse cases 1–4 | see [`security-review.md`](security-review.md), item 7 |

**Full suite:** `make test` → 6952 passed, 1 failed (`test_issue_485_a_spawned_server_and_its_pane_hold_no_secret`).
That test spawns a real tmux server, passes on rerun, and is unrelated to this diff
([`verification.md`](verification.md) V3).
