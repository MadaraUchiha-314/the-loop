---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#503"
---

# Unit and abuse-case tests (T1, T8)

All 37 unit tests pass, and the 13 abuse-case tests are among them. The same file fails
23 tests on `origin/main` (20.3.0), which is the red half of red → green.

Each run unsets `THE_LOOP_CLI_CONFIG`. A the-loop session exports it pointing at the
operator's live config, and inherited, it skews unrelated tests. CI never sets it.

## T1: `cd cli && uv run python -m pytest -q tests/test_slack_gateway_read_mode.py`

```text
test_slack_gateway_read_mode.py::test_gateway_is_a_read_mode_and_keeps_its_value_beside_a_block PASSED
test_slack_gateway_read_mode.py::test_the_poll_reader_never_starts_in_gateway_mode PASSED
test_slack_gateway_read_mode.py::test_the_reconciliation_read_is_allowed_in_gateway_mode PASSED
test_slack_gateway_read_mode.py::test_gateway_mode_with_a_block_is_push_reachable_and_interactive PASSED
test_slack_gateway_read_mode.py::test_poll_and_off_stay_unreachable_beside_a_block[poll] PASSED
test_slack_gateway_read_mode.py::test_poll_and_off_stay_unreachable_beside_a_block[off] PASSED
test_slack_gateway_read_mode.py::test_socket_without_a_block_is_unchanged PASSED
test_slack_gateway_read_mode.py::test_the_grants_still_decide_under_gateway PASSED
test_slack_gateway_read_mode.py::test_the_picker_is_refused_at_press_time_once_the_block_is_gone PASSED
test_slack_gateway_read_mode.py::test_abuse_gateway_without_a_block_reads_nothing_and_says_why PASSED
test_slack_gateway_read_mode.py::test_abuse_gateway_without_a_block_skips_the_reconciliation_read PASSED
test_slack_gateway_read_mode.py::test_abuse_a_block_without_a_url_is_no_gateway PASSED
test_slack_gateway_read_mode.py::test_abuse_an_unknown_mode_still_resolves_to_off PASSED
test_slack_gateway_read_mode.py::test_abuse_a_hand_built_gateway_config_without_the_flag_is_unreachable PASSED
test_slack_gateway_read_mode.py::test_abuse_only_an_explicit_socket_without_a_block_enables_the_listener[gateway-True-False] PASSED
test_slack_gateway_read_mode.py::test_abuse_only_an_explicit_socket_without_a_block_enables_the_listener[gateway-False-False] PASSED
test_slack_gateway_read_mode.py::test_abuse_only_an_explicit_socket_without_a_block_enables_the_listener[socket-True-False] PASSED
test_slack_gateway_read_mode.py::test_abuse_only_an_explicit_socket_without_a_block_enables_the_listener[socket-False-True] PASSED
test_slack_gateway_read_mode.py::test_abuse_only_an_explicit_socket_without_a_block_enables_the_listener[poll-False-False] PASSED
test_slack_gateway_read_mode.py::test_abuse_only_an_explicit_socket_without_a_block_enables_the_listener[off-False-False] PASSED
test_slack_gateway_read_mode.py::test_socket_beside_a_block_keeps_interactivity PASSED
test_slack_gateway_read_mode.py::test_abuse_channels_listen_refuses_beside_a_block_before_any_token[gateway] PASSED
test_slack_gateway_read_mode.py::test_abuse_channels_listen_refuses_beside_a_block_before_any_token[socket] PASSED
test_slack_gateway_read_mode.py::test_channels_listen_refuses_gateway_mode_without_a_block PASSED
test_slack_gateway_read_mode.py::test_status_row_names_the_gateway_in_gateway_mode PASSED
test_slack_gateway_read_mode.py::test_status_row_names_the_missing_block PASSED
test_slack_gateway_read_mode.py::test_the_generic_detail_is_unchanged_for_poll PASSED
test_slack_gateway_read_mode.py::test_socket_beside_gateway[socket-True-True] PASSED
test_slack_gateway_read_mode.py::test_socket_beside_gateway[gateway-True-False] PASSED
test_slack_gateway_read_mode.py::test_socket_beside_gateway[socket-False-False] PASSED
test_slack_gateway_read_mode.py::test_the_gateway_client_warns_once_about_socket_beside_it[socket-True] PASSED
test_slack_gateway_read_mode.py::test_the_gateway_client_warns_once_about_socket_beside_it[gateway-False] PASSED
test_slack_gateway_read_mode.py::test_channels_status_in_gateway_mode PASSED
test_slack_gateway_read_mode.py::test_channels_status_flags_gateway_mode_without_a_block PASSED
test_slack_gateway_read_mode.py::test_channels_status_flags_socket_beside_a_block PASSED
test_slack_gateway_read_mode.py::test_channels_status_socket_without_a_block_is_unchanged PASSED
test_slack_gateway_read_mode.py::test_channels_status_poll_beside_a_block_names_gateway_as_the_step PASSED
============================== 37 passed in 0.52s ==============================
```

## T8: `… tests/test_slack_gateway_read_mode.py -k abuse`

```text
test_slack_gateway_read_mode.py::test_abuse_gateway_without_a_block_reads_nothing_and_says_why PASSED
test_slack_gateway_read_mode.py::test_abuse_gateway_without_a_block_skips_the_reconciliation_read PASSED
test_slack_gateway_read_mode.py::test_abuse_a_block_without_a_url_is_no_gateway PASSED
test_slack_gateway_read_mode.py::test_abuse_an_unknown_mode_still_resolves_to_off PASSED
test_slack_gateway_read_mode.py::test_abuse_a_hand_built_gateway_config_without_the_flag_is_unreachable PASSED
test_slack_gateway_read_mode.py::test_abuse_only_an_explicit_socket_without_a_block_enables_the_listener[gateway-True-False] PASSED
test_slack_gateway_read_mode.py::test_abuse_only_an_explicit_socket_without_a_block_enables_the_listener[gateway-False-False] PASSED
test_slack_gateway_read_mode.py::test_abuse_only_an_explicit_socket_without_a_block_enables_the_listener[socket-True-False] PASSED
test_slack_gateway_read_mode.py::test_abuse_only_an_explicit_socket_without_a_block_enables_the_listener[socket-False-True] PASSED
test_slack_gateway_read_mode.py::test_abuse_only_an_explicit_socket_without_a_block_enables_the_listener[poll-False-False] PASSED
test_slack_gateway_read_mode.py::test_abuse_only_an_explicit_socket_without_a_block_enables_the_listener[off-False-False] PASSED
test_slack_gateway_read_mode.py::test_abuse_channels_listen_refuses_beside_a_block_before_any_token[gateway] PASSED
test_slack_gateway_read_mode.py::test_abuse_channels_listen_refuses_beside_a_block_before_any_token[socket] PASSED
====================== 13 passed, 24 deselected in 0.12s =======================
```

## Red on `origin/main`

These are the same two test files, copied into a worktree of `origin/main` at `0d45100`
(20.3.0) and run there:

```text
ERROR    the-loop.channels:slack.py:3586 channels.slack.read.mode is 'off' — set it to 'socket' to listen
ERROR    the-loop.channels:slack.py:3594 slack: Socket Mode needs both tokens — export THE_LOOP_SLACK_APP_TOKEN (xapp-, connections:write) and THE_LOOP_SLACK_BOT_TOKEN (xoxb-)
FAILED tests/test_slack_gateway_read_mode_integration.py::test_a_gateway_mode_instance_renders_the_approve_pair
FAILED tests/test_slack_gateway_read_mode.py::test_gateway_is_a_read_mode_and_keeps_its_value_beside_a_block
FAILED tests/test_slack_gateway_read_mode.py::test_the_reconciliation_read_is_allowed_in_gateway_mode
FAILED tests/test_slack_gateway_read_mode.py::test_gateway_mode_with_a_block_is_push_reachable_and_interactive
FAILED tests/test_slack_gateway_read_mode.py::test_poll_and_off_stay_unreachable_beside_a_block[poll]
FAILED tests/test_slack_gateway_read_mode.py::test_poll_and_off_stay_unreachable_beside_a_block[off]
FAILED tests/test_slack_gateway_read_mode.py::test_socket_without_a_block_is_unchanged
FAILED tests/test_slack_gateway_read_mode.py::test_the_grants_still_decide_under_gateway
FAILED tests/test_slack_gateway_read_mode.py::test_abuse_gateway_without_a_block_reads_nothing_and_says_why
FAILED tests/test_slack_gateway_read_mode.py::test_abuse_a_hand_built_gateway_config_without_the_flag_is_unreachable
FAILED tests/test_slack_gateway_read_mode.py::test_socket_beside_a_block_keeps_interactivity
FAILED tests/test_slack_gateway_read_mode.py::test_abuse_channels_listen_refuses_beside_a_block_before_any_token[gateway]
FAILED tests/test_slack_gateway_read_mode.py::test_abuse_channels_listen_refuses_beside_a_block_before_any_token[socket]
FAILED tests/test_slack_gateway_read_mode.py::test_status_row_names_the_missing_block
FAILED tests/test_slack_gateway_read_mode.py::test_the_generic_detail_is_unchanged_for_poll
FAILED tests/test_slack_gateway_read_mode.py::test_socket_beside_gateway[socket-True-True]
FAILED tests/test_slack_gateway_read_mode.py::test_socket_beside_gateway[gateway-True-False]
FAILED tests/test_slack_gateway_read_mode.py::test_socket_beside_gateway[socket-False-False]
FAILED tests/test_slack_gateway_read_mode.py::test_the_gateway_client_warns_once_about_socket_beside_it[socket-True]
FAILED tests/test_slack_gateway_read_mode.py::test_channels_status_in_gateway_mode
FAILED tests/test_slack_gateway_read_mode.py::test_channels_status_flags_gateway_mode_without_a_block
FAILED tests/test_slack_gateway_read_mode.py::test_channels_status_flags_socket_beside_a_block
FAILED tests/test_slack_gateway_read_mode.py::test_channels_status_poll_beside_a_block_names_gateway_as_the_step
23 failed, 17 passed in 0.77s
```
