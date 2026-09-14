---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#363"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: surviving a machine loss

> Derived from `bugfix.md` and `design.md`, **before** `tasks.md` — each task's `_Test:_`
> names a row of the matrix below. Authored at `test-planning`, completed at
> `verification`. See `reference/testing.md`.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. Every row runs against temporary directories and fake providers; this work
> item needs no credentials, reaches no network, and spawns no harness.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the recovery vocabulary: which `loop:` labels count as advancement (including the adhoc loop's `implementation` start), what `context_lost` answers for each combination of label/self-authored comment, and that the notice carries no caller-supplied text | `uv run --project cli python -m pytest -q cli/tests/test_recovery.py` |
| T2 | Unit | yes | `ControlStore.record_graph_position` and `record_frozen_graph` each preserve the other's key in the `graph` section (R2.1), and `graph_position` returns `None` for a record that has none | `uv run --project cli python -m pytest -q cli/tests/test_control.py cli/tests/test_workitem.py` |
| T3 | Unit | yes | `TmuxRunner.deliver` reports a **transient** failure inside the grace window and a **missing** session outside it (R4.1, R4.2), with `spawnGraceSeconds: 0` restoring today's behaviour (R4.3) and an unparseable `createdAt` treated as outside | `uv run --project cli python -m pytest -q cli/tests/test_tmux_runner.py` |
| T4 | Unit | yes | `event_labels` reads both payload shapes (`issue`, `pull_request`) and ignores malformed entries | `uv run --project cli python -m pytest -q cli/tests/test_routing.py` |
| T5 | Integration (scenario) | yes | **the reporter's sequence, on a fresh state root.** A work item labelled `loop:implementation` with an approved gate and an old `the-loop execute` on its thread, seen for the first time by a daemon that has never heard of it: no `graph.advanced` out of the start node, no `control.command`, the whole thread baselined, one notice posted, and the spawn still happening (R1.1, R1.2, R1.4, R3.1, R3.3) | `uv run --project cli python -m pytest -q cli/tests/test_recovery_integration.py` |
| T6 | Integration (scenario) | yes | the same daemon, same item, **with** a portable `position`: the state file is restored byte-for-byte, `Runtime.start` is the no-op it already is, and the item keeps walking from where it was (R2.2, R2.3) | `uv run --project cli python -m pytest -q cli/tests/test_recovery_integration.py` |
| T7 | Integration (scenario) | yes | issue-119 is intact: a genuinely new item whose thread already carries an authorized `the-loop execute` still has that command forwarded and still starts (R3.2), and an unlabelled item still enters its graph at the start node (R1.3) | `uv run --project cli python -m pytest -q cli/tests/test_recovery_integration.py` |
| T8 | Integration (scenario) | yes | a comment delivered three seconds after a spawn lands in the booting pane's session rather than respawning over it — one `session.spawned`, no `session.resume_failed`, no `session.respawned` (R4.1) | `uv run --project cli python -m pytest -q cli/tests/test_recovery_integration.py` |
| T9 | Unit | yes | the spawn prompt carries the recovery notice for a labelled item with no pointer, and renders byte-identical to today's for an ordinary spawn (R5.1, R5.2); the shipped template and `DEFAULT_SPAWN_TEMPLATE` stay byte-identical | `uv run --project cli python -m pytest -q cli/tests/test_interaction.py cli/tests/test_recovery.py` |
| T10 | Contract (OpenAPI / GraphQL SDL) | n/a — no HTTP surface changes. The control-plane API exposes sessions and events, not the portable `graph` section's internal keys, and `docs/api-specs/` is untouched | | |
| T11 | Migration / upgrade | yes | a portable record written before this change (no `position`) reads as "nothing to restore" and neither raises nor rewinds; the new schema key is absent-tolerant and a config that never sets it gets the default | `uv run --project cli python -m pytest -q cli/tests/test_state_portability.py cli/tests/test_cli_config.py` |
| T12 | Security / abuse case | yes | the four abuse cases of `bugfix.md` § Security considerations: a forged `loop:complete` label buys a refusal and never a node id; a portable `position` never overwrites an existing `graph-state.json`; the age rule never makes an unauthorized comment executable; the notice cannot echo a commenter's body | `uv run --project cli python -m pytest -q cli/tests/test_recovery.py cli/tests/test_recovery_integration.py -k abuse` |
| T13 | UI / visual | n/a — no rendered surface. The only human-visible output is a ticket comment, whose text is asserted at T1 | | |
| T14 | Snapshot | n/a — the payloads asserted here (a restored state file, a prompt) are compared verbatim at T6 and T9, which is a snapshot without the indirection | | |
| T15 | Performance / load | n/a — one extra file read per graph start and one extra write per graph transition, both on paths that already read and write that file; the poller's addition is a scan of comments it has already fetched | | |
| T16 | Accessibility | n/a — no rendered UI | | |
| T17 | Manual exploratory | n/a — the defect's trigger is a machine that no longer exists. T5–T8 reproduce it deterministically from the reporter's event log, which is what a manual run could not do | | |
| T18 | Repository gates | yes | the whole repository still passes what CI runs: ruff, ruff format, pyright, config validation (both schema copies byte-identical), the full suite, and markdownlint over every `**/*.md` including these artifacts | `make check` |

## Verification environment

A single checkout and `uv sync`. Every scenario builds its own temporary state root,
checkout and fake GitHub provider through the existing fixtures in `cli/tests/conftest.py`
and the poller/dispatcher test helpers; no service, no credential, no `gh`, no `tmux`
binary (the runner is driven through its injected command runner). Evidence is the raw
pytest and `make check` output, committed under `evidence/`.

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R3.1 | `test_a_phase_label_past_the_start_node_is_evidence_of_work` |
| T1 | R1.3 | `test_an_unlabelled_item_and_a_start_phase_label_are_not_evidence` |
| T1 | R3.1 | `test_the_loops_own_comment_is_evidence_even_without_a_label` |
| T1 | R3.3, T12 | `test_the_notice_carries_only_minted_values` |
| T2 | R2.1 | `test_recording_a_position_keeps_the_frozen_selection` / `test_recording_a_selection_keeps_the_position` |
| T3 | R4.1 | `test_a_session_still_inside_its_grace_window_is_not_reported_missing` |
| T3 | R4.2 | `test_a_session_past_its_grace_window_is_reported_missing` |
| T3 | R4.3 | `test_a_zero_grace_window_restores_the_immediate_verdict` |
| T4 | R1.1, R5.1 | `test_event_labels_reads_an_issue_and_a_pull_request` |
| T5 | R1.1, R1.2, R1.4 | `test_a_forgotten_item_is_not_rewound_and_still_gets_a_session` |
| T5 | R1.1 | `test_an_event_on_a_forgotten_item_does_not_advance_it_either` — `advance` reads an empty state as the start node too |
| T5 | R1.1 | `test_a_corrupt_state_file_refuses_rather_than_rewinding` — a file that will not parse is not a pointer |
| T5 | R3.1, R3.3 | `test_a_forgotten_items_old_commands_are_baselined_and_announced_once` |
| T6 | R2.2, R2.3 | `test_a_published_position_is_restored_byte_for_byte` |
| T7 | R3.2 | `test_a_new_items_pending_start_command_is_still_forwarded` |
| T7 | R1.3 | `test_an_item_with_no_phase_label_still_enters_the_graph` |
| T8 | R4.1 | `test_a_comment_arriving_during_the_boot_does_not_spawn_a_second_session` |
| T9 | R5.1 | `test_a_recovery_spawn_prompt_says_the_conversation_is_gone` |
| T9 | R5.2 | `test_an_ordinary_spawn_prompt_is_unchanged` |
| T11 | R2.2 | `test_a_record_without_a_position_reads_as_nothing_to_restore` |
| T12 | bugfix.md §AC1 | `test_abuse_a_forged_complete_label_never_places_a_pointer` |
| T12 | bugfix.md §AC2 | `test_abuse_a_portable_position_never_overwrites_local_state` |
| T12 | bugfix.md §AC3 | `test_abuse_an_unauthorized_command_is_still_never_executed` |
| T18 | R6.1 | `make check` — the suite, both schema copies, markdownlint over these artifacts |

## Verification results

> Filled in at `verification`. Every row marked `yes` above is ticked here, with the
> command, the outcome, and where the evidence is committed.

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_recovery.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_control.py cli/tests/test_workitem.py`
- [x] T3 — `uv run --project cli python -m pytest -q cli/tests/test_tmux_runner.py`
- [x] T4 — `uv run --project cli python -m pytest -q cli/tests/test_routing.py`
- [x] T5 — `uv run --project cli python -m pytest -q cli/tests/test_recovery_integration.py`
- [x] T6 — `uv run --project cli python -m pytest -q cli/tests/test_recovery_integration.py`
- [x] T7 — `uv run --project cli python -m pytest -q cli/tests/test_recovery_integration.py`
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests/test_recovery_integration.py`
- [x] T9 — `uv run --project cli python -m pytest -q cli/tests/test_interaction.py cli/tests/test_recovery.py`
- [x] T11 — `uv run --project cli python -m pytest -q cli/tests/test_state_portability.py cli/tests/test_cli_config.py`
- [x] T12 — `uv run --project cli python -m pytest -q cli/tests/test_recovery.py cli/tests/test_recovery_integration.py -k abuse`
- [x] T18 — `make check`

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
| The failing state: the five scenarios that reproduce the reporter's sequence, before the fix | `pytest -q cli/tests/test_recovery.py cli/tests/test_recovery_integration.py` | fail (red, as designed) | [`evidence/red.md`](evidence/red.md) |
| T1–T12 — the vocabulary, the portable position, the grace window, the labels reader, the five scenarios, the prompt, the upgrade path and the abuse cases | the commands ticked above | pass | [`evidence/verification.md`](evidence/verification.md) |
| T18 — every repository gate CI runs | `make check` | pass | [`evidence/verification.md`](evidence/verification.md) |
