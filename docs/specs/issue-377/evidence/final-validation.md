---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#377"
---

<!-- Authored per the the-loop:writing skill. -->

# Final validation: a released work item is launched with the arguments the operator declared

> The `verification` node's proof: every activity in `testing-plan.md` ticked, with the
> command, the outcome and the committed artifact.

## Red → green

The two tests the ticket asked for, and the six beside them, were run **before** the fix
(only `launch_args` existed at that point, so the resolver's own unit tests were already
green). Verbatim from that run:

```text
FAILED test_spawn_gate_integration.py::test_a_released_session_is_launched_with_every_configured_harness_argument
E   AssertionError: assert [] == ['--dangerously-skip-permissions']
FAILED test_spawn_gate_integration.py::test_the_session_spawned_by_the_gate_answering_reply_runs_on_the_model_it_froze
E   AssertionError: assert [] == ['--dangerously-skip-permissions', '--model', 'opus-5']
FAILED test_spawn_gate_integration.py::test_abuse_a_forged_model_in_the_state_file_buys_nothing_on_the_post_gate_spawn
E   AssertionError: assert [] == ['--dangerously-skip-permissions']
FAILED test_dispatcher_choice.py::test_the_choice_path_starts_from_the_shared_adapters_own_arguments
E   At index 0 diff: '--dangerously-skip-permissions' != '--only-the-adapter-knows-this'
FAILED test_dispatcher_choice.py::test_the_respawned_event_names_the_argv_it_was_relaunched_on
E   KeyError: 'harness_args'
FAILED test_standing.py::test_an_entry_inherits_the_harnesses_args_declared_in_their_new_home
E   AssertionError: assert () == ('--dangerously-skip-permissions',)
FAILED test_standing_integration.py::test_a_created_session_inherits_the_harnesses_args_declared_in_their_new_home
E   AssertionError: assert () == ('--dangerously-skip-permissions',)
FAILED test_models_cmd.py::test_check_probes_with_the_arguments_a_session_is_launched_with
E   AssertionError: assert [[]] == [['--dangerously-skip-permissions']]
8 failed, 4 passed, 114 deselected
```

The first line is the bug as reported: a released session recorded with no arguments.
The second is the defect found beside it: the model the gate froze not reaching the
session that gate spawned. After the fix all eight pass (below).

## Results

| # | Command | Outcome | Artifact |
|---|---|---|---|
| T1 | `pytest cli/tests/test_modelchoice.py` | pass (39 tests) — the new home, the deprecated home, the caller's parsed routing args, both homes (new wins; `launch_args` warns and `config_findings` reports `harnesses[claude].args`), nothing declared, a non-list `args` | `test_launch_args_*` (6 tests) |
| T2 | `pytest cli/tests/test_spawn_gate_integration.py` | pass — through `poller.daemon._build_dispatcher`, a config declaring the flag under `harnesses[].args` only: the released session's record and its `session.spawned` event both carry `['--dangerously-skip-permissions']`, `gh_event: issue_comment` | `test_a_released_session_is_launched_with_every_configured_harness_argument` |
| T3 | same file | pass — `routing.harnessArgs` alone still reaches the released session | `test_the_deprecated_routing_harness_args_still_reach_a_released_session` |
| T4 | same file | pass — the gate double freezes `opus-5` into `work-item-state.json` on `on_arm`; the spawned record carries `[flag, --model, opus-5]` and `model: opus-5`; a second comment is delivered into it (`spawns == 1`) | `test_the_session_spawned_by_the_gate_answering_reply_runs_on_the_model_it_froze` |
| T5 | `pytest cli/tests/test_dispatcher_choice.py` | pass (25 tests) — the fixture now builds its adapter through `launch_args`; a work item that chose nothing records `['--dangerously-skip-permissions']` with `harness_args={}` in the routing config; the choice path's argv starts with whatever the adapter carries | `test_a_work_item_that_chose_nothing_launches_on_the_declared_arguments`, `test_the_choice_path_starts_from_the_shared_adapters_own_arguments`, and the 23 issue-358 tests unmodified |
| T6 | both files | pass — `session.spawned` carries `harness_args`; `session.respawned` carries `harness_args` and `model`, and the respawned record carries the model the relaunch resolved | `test_a_released_session_is_launched_with_every_configured_harness_argument`, `test_the_respawned_event_names_the_argv_it_was_relaunched_on` |
| T7 | `pytest cli/tests/test_standing.py cli/tests/test_standing_integration.py` | pass (84 tests) — a declared entry and a created session both inherit `harnesses[].args`; an explicit `[]` still means none; the two pre-existing inheritance tests on the deprecated key pass unmodified | `test_an_entry_inherits_the_harnesses_args_declared_in_their_new_home`, `test_a_created_session_inherits_the_harnesses_args_declared_in_their_new_home` |
| T8 | `pytest cli/tests/test_models_cmd.py` | pass (9 tests) — the probe adapter's `extra_args` is `['--dangerously-skip-permissions']` | `test_check_probes_with_the_arguments_a_session_is_launched_with` |
| T9 | both integration files | pass — a forged `smuggled-9` frozen by the gate reply yields `harness_args == [flag]` and `model == ""`; the issue-358 abuse table passes against the rewired fixture | `test_abuse_a_forged_model_in_the_state_file_buys_nothing_on_the_post_gate_spawn`, `test_abuse_*` in `test_dispatcher_choice.py` |
| T10 | `uv run --project cli python -m pytest -q cli` | pass — see § Gates | — |
| T11 | `pytest cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py cli/tests/test_api_contract_parity.py cli/tests/test_routing.py cli/tests/test_eventlog_integration.py` | pass (211 tests) — docs parity, schema-copy parity, the OpenAPI surface, the event catalogue and the end-to-end `session.spawned` scenario | existing suites |
| T12 | — | n/a — no route, parameter or schema shape changed; the parity test compares paths, methods and operationIds | — |
| T13 | — | n/a — the daemon composition is under test in T2–T4 with the runner and binary stubbed | — |
| T14 | — | n/a — one dict at build time; one fewer config read per spawn | — |
| T15 | manual, on a devbox | **not run here** — this session has no `tmux`, no harness binary and no live work item. The procedure is the report's own: with the flag under `harnesses[].args`, label an issue, answer the gate, then `ps -eo pid,cmd \| grep "[c]laude --session-id"` shows the flag and `the-loop events --type session.spawned` shows `harness_args` | — |

## Gates

```text
uv run ruff check cli hooks                       → All checks passed!
uv run ruff format --check cli hooks              → 315 files already formatted
uv run pyright cli                                → 0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py          → VALID ×3
markdownlint-cli2 (changed and new .md files)     → 0 error(s)
uv run --project cli python -m pytest -q cli      → 3896 passed, 1 skipped
```
