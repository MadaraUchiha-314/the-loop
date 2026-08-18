# Red run — the tests that motivate the change (issue-270)

Captured before any production code changed: at this point only `cli/tests/*` and the
spec chain exist, so every failure below is the reported bug.

## Command

```console
$ uv run --project cli python -m pytest -q \
    cli/tests/test_routing.py cli/tests/test_poller.py \
    cli/tests/test_poller_integration.py cli/tests/test_interaction.py \
    -k "settle or settled or deduper_remembers or pre_start or older_version or whole_thread"
```

## Output

```text
=========================== short test summary info ============================
FAILED cli/tests/test_routing.py::test_router_deduper_remembers_a_delivery_outcome
FAILED cli/tests/test_routing.py::test_a_comment_refused_awaiting_start_settles_its_delivery
FAILED cli/tests/test_routing.py::test_a_spawn_policy_drop_still_releases_its_id_and_settles_nothing
FAILED cli/tests/test_routing.py::test_a_paused_session_settles_the_delivery_it_suppresses
FAILED cli/tests/test_routing.py::test_a_pause_between_enqueue_and_dispatch_settles_the_delivery
FAILED cli/tests/test_routing.py::test_a_delivery_a_session_received_outranks_a_settlement
FAILED cli/tests/test_routing.py::test_an_executed_control_command_settles_its_delivery
FAILED cli/tests/test_routing.py::test_a_rejected_control_command_settles_its_delivery
FAILED cli/tests/test_routing.py::test_conflicting_control_keywords_settle_the_delivery
FAILED cli/tests/test_poller.py::test_a_synchronously_settled_comment_is_baselined_with_no_attempt
FAILED cli/tests/test_poller.py::test_a_comment_settled_after_an_attempt_is_resolved_next_cycle
FAILED cli/tests/test_poller.py::test_a_settled_comment_is_never_abandoned_so_an_upgrade_replays_nothing
FAILED cli/tests/test_poller.py::test_a_settled_comment_reports_no_delivery_failure
FAILED cli/tests/test_poller.py::test_a_settled_presence_resolves_the_spawn_ledger
FAILED cli/tests/test_poller_integration.py::test_a_pre_start_comment_is_refused_once_and_never_counted_again
FAILED cli/tests/test_poller_integration.py::test_a_ledger_left_pending_by_an_older_version_settles_on_the_next_cycle
FAILED cli/tests/test_interaction.py::test_the_spawn_prompt_tells_the_session_to_read_the_whole_thread
17 failed, 343 deselected in 0.91s
```

## What each failure says

| Test | Pre-fix behaviour it pins |
|---|---|
| `test_router_deduper_remembers_a_delivery_outcome` | the dedup entry holds no outcome — there is nowhere to say "done with this" |
| `test_a_comment_refused_awaiting_start_settles_its_delivery` | the ticket's case: the refusal reads back as `inflight` |
| `test_a_paused_session_settles_the_delivery_it_suppresses` · `…pause_between_enqueue_and_dispatch…` | the same for a paused session, on both the synchronous and the asynchronous path |
| `test_a_delivery_a_session_received_outranks_a_settlement` | precedence: a real delivery must still win |
| `test_an_executed_control_command_settles_its_delivery` · `…rejected…` · `…conflicting_control_keywords…` | a consumed control comment is accounted for as a pending delivery |
| `test_a_spawn_policy_drop_still_releases_its_id_and_settles_nothing` | the control: `spawn-policy` must keep releasing its id (it fails only because `delivery_outcome` does not exist yet) |
| `test_a_synchronously_settled_comment_is_baselined_with_no_attempt` | `commentAttempts: {IC_1: 1}` — the reported symptom |
| `test_a_comment_settled_after_an_attempt_is_resolved_next_cycle` | a later settlement never clears the counter |
| `test_a_settled_comment_is_never_abandoned_so_an_upgrade_replays_nothing` | the refusal is written into `gaveUp`, which a later version re-arms — an accidental replay |
| `test_a_settled_comment_reports_no_delivery_failure` | `poll.comment_failed` and a give-up notice on the ticket for a delivery nobody attempted |
| `test_a_settled_presence_resolves_the_spawn_ledger` | a refused presence spends the spawn budget |
| `test_a_pre_start_comment_is_refused_once_and_never_counted_again` | the reproduction, end to end, including the restart |
| `test_a_ledger_left_pending_by_an_older_version_settles_on_the_next_cycle` | an existing stuck ledger is retried rather than resolved |
| `test_the_spawn_prompt_tells_the_session_to_read_the_whole_thread` | nothing tells the spawned session to read what was never delivered |
