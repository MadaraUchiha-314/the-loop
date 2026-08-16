# Evidence: Python tests (issue-239)

Testing-plan rows **T1** (unit), **T3** (integration, Gherkin), **T8** (capacity) and
**T9** (abuse cases). Commands run from the project root, as CI runs them.

## The whole suite

```text
E           assert 0 == 68126

cli/tests/test_poll_daemon_integration.py:196: AssertionError
=========================== short test summary info ============================
FAILED cli/tests/test_core_repo.py::test_critics_lists_configured_entries_without_argv
FAILED cli/tests/test_critics.py::test_list_reports_availability - assert Tru...
FAILED cli/tests/test_harness_gate.py::TestAttemptsFile::test_a_work_item_with_slashes_does_not_escape_the_temp_dir
FAILED cli/tests/test_poll_daemon_integration.py::test_start_detaches_a_poller_that_owns_its_pidfile_and_log
4 failed, 2149 passed in 102.96s (0:01:42)
```

**Five failures, none of them this work item's.** Four fail identically on `origin/main`
(verified by running them on a stashed tree); the fifth is load-flaky and filed as
[#251](https://github.com/MadaraUchiha-314/the-loop/issues/251) — it waits on the spawn and
asserts on the registration, and a file that only burns 16 seconds of wall-clock reproduces
it 1 in 6. The stream's own tests are all in the 2148 that pass.

## T1 — unit: the config, the tailer, the cursor, the broker

```text
...............................                                          [100%]
31 passed in 0.04s
```

## T3/T8/T9 — the stream against a live uvicorn on a loopback port

```text
test_an_appended_event_reaches_an_open_subscriber PASSED [  7%]
test_a_work_item_filter_excludes_another_items_events PASSED [ 14%]
test_the_control_planes_own_api_requests_never_reach_the_stream PASSED [ 21%]
test_a_reconnect_with_last_event_id_replays_exactly_the_missed_records PASSED [ 28%]
test_an_idle_stream_is_kept_alive PASSED [ 35%]
test_the_retry_directive_sets_the_browsers_reconnect_delay PASSED [ 42%]
test_the_rest_surface_still_answers_with_the_stream_at_capacity PASSED [ 50%]
test_abuse_a_connection_beyond_the_maximum_is_refused PASSED [ 57%]
test_a_disconnect_releases_the_slot PASSED [ 64%]
test_abuse_a_malformed_cursor_is_refused_rather_than_ignored PASSED [ 71%]
test_abuse_a_malformed_filter_is_refused_rather_than_streaming_everything PASSED [ 78%]
test_abuse_replay_from_far_behind_is_bounded_and_the_client_is_told PASSED [ 85%]
test_a_disabled_stream_answers_404 PASSED [ 92%]
test_the_stream_is_instrumented_like_everything_else PASSED [100%]
============================= 14 passed in 17.42s ==============================
```

## T9 alone — the abuse cases

```text
....                                                                     [100%]
4 passed, 10 deselected in 3.29s
```

## T8 alone — the REST surface with the stream at capacity

```text
.                                                                        [100%]
1 passed, 13 deselected in 1.19s
```

`-k capacity` selects `test_the_rest_surface_still_answers_with_the_stream_at_capacity`,
which is the R5.1 assertion: with every allowed connection open and idle,
`GET /api/v1/health` and `GET /api/v1/work-items` both still answer. The mechanism behind
it is that the route is `async def` rather than `def` — a synchronous generator would hold
one of the anyio threadpool's 40 slots for the life of each connection — and the test
asserts the property rather than the mechanism, so a refactor back to `def` fails here.
