# Unit, performance and migration tests (T1, T7, T10)

Run on 2026-11-20 at `82db8f0a`, from `cli/`, with `THE_LOOP_CLI_CONFIG`,
`THE_LOOP_INSTANCE` and `THE_LOOP_WORK_ITEM` unset. A daemon-spawned session exports
those, and with them set some unrelated status tests read the live daemon.

| Row | Command | Result |
|---|---|---|
| T1 | `uv run python -m pytest -q tests/test_session_state.py tests/test_stop_check.py tests/test_durations.py tests/test_graph_claim_assignment.py tests/test_configschema.py tests/test_eventlog.py` | 304 passed in 9.66s |
| T7 | `uv run python -m pytest -q tests/test_session_state.py -k cycle_budget --durations=1` | 1 passed; the cycle over 50 work items and a 50,000-line log took 0.70 s (bound: 2 s) |
| T10 | `uv run python -m pytest -q tests/test_harness_gate.py` | 85 passed in 1.90s |
| T10 | `uv run python -m pytest -q tests/test_session_state.py -k legacy` | 5 passed, 94 deselected in 0.18s |

Tests the plan did not name, added during implementation and run in the whole
suite: `tests/test_watchconfig.py`, `tests/test_watchdog.py`,
`tests/test_channels_sessionnotes.py`, `tests/test_claim_assignment_integration.py`.

## Migration cases (T10)

- A config with neither new block loads with the defaults:
  `test_a_config_without_the_blocks_loads_with_the_defaults` (`tests/test_watchconfig.py`).
- This plugin's hook against a CLI without `stop-check` falls back to `check` and
  still applies the P3 fix: `TestTheGateAsksTheService` fallback cases and
  `test_a_wait_before_the_pointer_counts_as_passed` (`tests/test_harness_gate.py`).
- An event log written before this change yields "not watched" and no nudge:
  `test_legacy_log_without_turn_records_is_not_watched`,
  `test_legacy_empty_log_is_not_watched`,
  `test_legacy_stall_records_alone_never_owe_a_nudge`.
- A turn-start hook with no CLI on the path is a silent no-op:
  `test_turn_start_without_cli_is_a_silent_no_op`.
- A `lastBlock` left by an old comment: the state file is not migrated. It clears
  on the next advance, as any block does, and no comment writes a new one
  (`tests/test_inbound_readonly_integration.py`).

## Red to green

Each task's commit message records its red run and its green run. The P3
regression: against the hook as committed before task 7, the scenario "the gate
gives up after its attempts and records why" failed with `assert 0 == 2` (the
stop was allowed). It passes at `a75a8b31`.
