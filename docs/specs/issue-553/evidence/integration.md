# Integration evidence — issue-553

Run at commit `3e8315d1`, from `cli/`, with this daemon session's `THE_LOOP_*` environment
variables unset (CI does not set them).

## Red before the change

The first full run after the graph declaration, before any test was changed, failed
exactly the tests that pin the graph's shape:

| File | Failed | What it pinned |
|---|---|---|
| `tests/test_graph_skips.py` | 2 | the node after `import-handoff`; the opt-in list |
| `tests/test_handoff_selection.py` | 2 | the two checklist snapshots |
| `tests/test_import_handoff.py` | 3 | the edge out of `import-handoff`; the demotion's node list |
| `tests/test_jira_format.py` | 1 | the Jira checklist snapshot |
| `tests/test_pdlc_e2e_integration.py` | 7 | each scenario's node trace |
| `tests/test_quiz.py` | 1 | `gather-context` had no command file yet |

New tests written before their code were red in turn: the five record tests for
`context-settled`, `test_chain_is_the_closed_set`, the command-listing parity test and
`test_the_artifact_rule_names_current_state_among_the_durable_files`.

## Green after

| Activity | Command | Result |
|---|---|---|
| T1, T2 | `uv run python -m pytest -q tests/test_graph_model.py tests/test_graph_skips.py tests/test_graph_catalog.py tests/test_graph_parity.py tests/test_init_commands.py tests/test_quiz.py tests/test_writing_parity.py` | 315 passed |
| T3, T8 (3–6) | `uv run python -m pytest -q tests/test_context_gate_integration.py` | 16 passed |
| T4, T8 (7) | `uv run python -m pytest -q tests/test_handoff_record.py tests/test_import_handoff.py tests/test_handoff_selection.py tests/test_handoff_pickup.py` | 192 passed |
| T5, T8 (8) | `uv run python -m pytest -q tests/test_graphlink_integration.py` | 17 passed |
| T6, T7 | `uv run python -m pytest -q tests/test_jira_integration.py tests/test_jira_format.py tests/test_pdlc_e2e_integration.py` | 74 passed |

`tests/test_jira_format.py` was added to the T6 command: it is the module that holds
the Jira checklist snapshot, which the plan's command did not name.

## New tests, by scenario

- *An opted-in work item gathers context and waits for its author* — three tests in
  `test_context_gate_integration.py`.
- *A work item that ticks neither row walks as before* — one test, plus the frozen-state
  cases.
- *A handoff at context settled enters at the context gate* — in
  `test_handoff_record.py`, `test_handoff_selection.py` and `test_import_handoff.py`.
- *A carried current-state file that fails verification demotes the walk* — in
  `test_import_handoff.py`.
- *Every later prompt names the current-state file once it exists* — in
  `test_graphlink_integration.py`.
