---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#505"
---

# Unit, abuse-case and migration tests (T1, T8, T10)

All 39 tests in `tests/test_gateway_rooms.py` pass. Against `origin/main` (20.4.0) code,
the new unit and integration files give 35 failed, 3 passed and 5 errors. That is the
red half of red → green. The 3 that pass check behaviour this change keeps: resolution
without a room, and `bind`'s held routing.

Captured 2026-10-20 on `feat/issue-505-gateway-channel-bindings`, from `cli/`, with
`THE_LOOP_CLI_CONFIG` unset. A the-loop session exports it pointing at the operator's
live config, and inherited, it skews unrelated tests.

## T1: `uv run python -m pytest -q tests/test_gateway_rooms.py`

```text
39 passed
tests/test_gateway_rooms.py::test_publish_rooms_records_and_resolves_a_room
tests/test_gateway_rooms.py::test_publishing_drains_the_rooms_held_events_in_order
tests/test_gateway_rooms.py::test_a_drained_event_waits_on_the_subject_until_a_claim
tests/test_gateway_rooms.py::test_the_drain_matches_the_channel_exactly_not_as_a_pattern
tests/test_gateway_rooms.py::test_an_already_routed_event_is_not_routed_again
tests/test_gateway_rooms.py::test_a_set_without_a_room_retracts_it_and_a_move_swaps_it
tests/test_gateway_rooms.py::test_abuse_a_live_holders_room_is_kept_and_the_rest_applied
tests/test_gateway_rooms.py::test_an_expired_holders_room_is_taken_over
tests/test_gateway_rooms.py::test_abuse_a_publication_never_retracts_another_instances_room
tests/test_gateway_rooms.py::test_abuse_a_second_peer_under_a_live_name_is_refused_and_nothing_applied
tests/test_gateway_rooms.py::test_pruning_a_lapsed_instance_drops_its_rooms
tests/test_gateway_rooms.py::test_the_instances_view_lists_rooms
tests/test_gateway_rooms.py::test_migration_a_store_without_the_rooms_table_gains_it
tests/test_gateway_rooms.py::test_bind_keeps_routing_held_events_after_the_refactor
tests/test_gateway_rooms.py::test_a_top_level_message_in_a_published_room_resolves_to_its_work_item
tests/test_gateway_rooms.py::test_a_thread_binding_beats_the_room
tests/test_gateway_rooms.py::test_a_published_room_beats_the_static_room
tests/test_gateway_rooms.py::test_without_a_room_resolution_is_unchanged
tests/test_gateway_rooms.py::test_a_slash_command_in_a_published_room_resolves
tests/test_gateway_rooms.py::test_put_rooms_publishes_and_reports_routed_and_refused
tests/test_gateway_rooms.py::test_put_rooms_reports_a_live_holders_room_as_refused
tests/test_gateway_rooms.py::test_the_instances_view_reports_each_instances_rooms
tests/test_gateway_rooms.py::test_abuse_an_instance_off_the_allow_list_is_refused
tests/test_gateway_rooms.py::test_abuse_a_second_peer_under_a_live_name_gets_409
tests/test_gateway_rooms.py::test_abuse_a_malformed_publication_is_422_and_stores_nothing[name]
tests/test_gateway_rooms.py::test_abuse_a_malformed_publication_is_422_and_stores_nothing[thread-key]
tests/test_gateway_rooms.py::test_abuse_a_malformed_publication_is_422_and_stores_nothing[bad-ref]
tests/test_gateway_rooms.py::test_abuse_a_malformed_publication_is_422_and_stores_nothing[long-ref]
tests/test_gateway_rooms.py::test_abuse_a_malformed_publication_is_422_and_stores_nothing[too-many]
tests/test_gateway_rooms.py::test_on_change_fires_after_a_changing_add_remove_and_clear
tests/test_gateway_rooms.py::test_on_change_failing_never_fails_the_declaration
tests/test_gateway_rooms.py::test_register_publishes_every_declared_room
tests/test_gateway_rooms.py::test_a_contested_channel_is_not_published
tests/test_gateway_rooms.py::test_the_reconcile_publishes_only_a_changed_set_after_the_interval
tests/test_gateway_rooms.py::test_register_publishes_the_full_set_even_when_unchanged
tests/test_gateway_rooms.py::test_a_failed_publish_is_logged_and_retried
tests/test_gateway_rooms.py::test_retraction_reaches_the_gateway
tests/test_gateway_rooms.py::test_abuse_an_unreadable_directory_retracts_nothing
tests/test_gateway_rooms.py::test_a_client_without_a_channel_store_publishes_no_rooms
```

## T8: `… tests/test_gateway_rooms.py tests/test_gateway_rooms_integration.py -k abuse`

```text
11 passed, 32 deselected
```

Abuse cases 1 (allow-list), 2 (live holder kept), 3 (another instance's room untouched),
5 (five malformed shapes → 422, nothing stored), a second peer under a live name (409),
and fail closed (an unreadable portable directory retracts nothing). Abuse case 4 (a
stranger's message still judged by the instance) is asserted in the first T2 scenario:
the gateway hands over the raw payload with its author. The instance's Slack pipeline,
which applies the principals, listen mode and `authorizedUsers`, is unchanged and keeps
its own tests (issue-496, issue-389).

## T10: `… tests/test_gateway_rooms.py -k migration`

```text
1 passed, 38 deselected
```

A store with the `rooms` table dropped (the 20.4.0 schema) reopens, keeps its bindings,
and gains the table.

## Red on `origin/main`

The two new test files were copied into a worktree of `origin/main` and run against that
tree's `the_loop`:

```text
35 failed, 3 passed, 5 errors in 1.24s
```
