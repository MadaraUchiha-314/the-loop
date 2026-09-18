---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#378"
---

<!-- Authored per the the-loop:writing skill. -->

# Final validation: a work item's whole life is told to every channel, and Slack can begin one

> The `verification` node's proof: every activity in `testing-plan.md` ticked, with the
> command, the outcome and the committed artifact.

## Red → green

The lifecycle suites were run before any production code existed. Verbatim tail of
that run (`pytest cli/tests/test_graph_lifecycle.py cli/tests/test_lifecycle_integration.py cli/tests/test_bus.py`):

```text
E       AssertionError: assert 'slack' not in '- no channe...ck.subscribe'
FAILED cli/tests/test_lifecycle_integration.py::test_a_closed_issue_is_announced_before_its_room_is_forgotten
FAILED cli/tests/test_lifecycle_integration.py::test_a_merged_pull_request_that_is_the_work_item_is_announced_as_merged
FAILED cli/tests/test_lifecycle_integration.py::test_a_dispatcher_without_a_publisher_closes_as_before
FAILED cli/tests/test_bus.py::test_the_lifecycle_rows_are_subscribable_never_publishable_never_recorded
FAILED cli/tests/test_bus.py::test_publish_lifecycle_builds_nothing_without_a_channels_section
FAILED cli/tests/test_bus.py::test_publish_lifecycle_never_records_and_never_raises
FAILED cli/tests/test_bus.py::test_the_daemon_lifecycle_publisher_reads_the_config_per_call
FAILED cli/tests/test_bus.py::test_the_notify_hooks_skipped_message_names_no_channel
ERROR cli/tests/test_graph_lifecycle.py::test_start_publishes_the_first_phase
ERROR cli/tests/test_graph_lifecycle.py::test_an_edge_into_another_phase_completes_one_and_starts_the_next
ERROR cli/tests/test_graph_lifecycle.py::test_two_nodes_sharing_a_phase_publish_nothing_between_them
ERROR cli/tests/test_graph_lifecycle.py::test_a_terminal_node_completes_its_phase
ERROR cli/tests/test_graph_lifecycle.py::test_cleanup_starts_its_phase_and_completes_none
ERROR cli/tests/test_graph_lifecycle.py::test_a_force_publishes_nothing - Att...
ERROR cli/tests/test_graph_lifecycle.py::test_a_config_without_channels_publishes_nothing_and_still_advances
ERROR cli/tests/test_graph_lifecycle.py::test_lifecycle_text_is_fixed_words_and_ids
ERROR cli/tests/test_graph_lifecycle.py::test_a_registered_provider_receives_the_lifecycle_with_no_slack_anywhere
```

The `/the-loop new` suite, before the verb existed (`pytest cli/tests/test_channels_commands.py`):

```text
FAILED cli/tests/test_channels_commands.py::test_new_opens_the_work_item_and_its_thread
FAILED cli/tests/test_channels_commands.py::test_new_falls_back_to_kickoff_repo_without_a_prefix
FAILED cli/tests/test_channels_commands.py::test_new_refuses_what_the_kickoff_refuses[new Just a title-repos0--no default repository]
FAILED cli/tests/test_channels_commands.py::test_new_refuses_what_the_kickoff_refuses[new nobody/x: title-repos1-o/r-don't know a repository]
FAILED cli/tests/test_channels_commands.py::test_new_refuses_what_the_kickoff_refuses[new r: title-repos2--more than one repository]
FAILED cli/tests/test_channels_commands.py::test_new_refuses_what_the_kickoff_refuses[new o/r:-repos3-o/r-said nothing else]
FAILED cli/tests/test_channels_commands.py::test_new_with_an_empty_title_is_refused
FAILED cli/tests/test_channels_commands.py::test_new_needs_the_create_grant
FAILED cli/tests/test_channels_commands.py::test_new_from_an_unlisted_member_creates_nothing
FAILED cli/tests/test_channels_commands.py::test_new_acts_once_per_trigger - ...
FAILED cli/tests/test_channels_commands.py::test_new_survives_a_thread_that_cannot_be_opened
FAILED cli/tests/test_channels_commands.py::test_new_when_the_ledger_refuses_is_a_recorded_outcome
FAILED cli/tests/test_channels_commands.py::test_usage_and_help_name_the_new_verb_and_its_grant
```

The room and provider tests (`test_channels_declared_integration.py`, `test_channels.py`)
failed the same way on `conversation_for`, `mode` and `CHANNEL_PROVIDERS` before the state,
channel and loader changes. After the change every one of them passes (below).

## Results

| # | Command | Outcome | Artifact |
|---|---|---|---|
| T1 | `pytest cli/tests/test_bus.py cli/tests/test_channels.py -k catalog or lifecycle_rows or docs_list` | pass — three rows, subscribable / not publishable / not recorded, `origin: loop`, disjoint from the notify vocabulary; the docs table lists them | `test_the_lifecycle_rows_are_subscribable_never_publishable_never_recorded`, `test_the_docs_list_every_subscribable_event` |
| T2 | `pytest cli/tests/test_bus.py -k publish_lifecycle or daemon_lifecycle` | pass — no section builds nothing; `record=False`; a raising bus is `False`; the getter is read per call and a raising getter publishes nothing | three tests |
| T3 | `pytest cli/tests/test_graph_lifecycle.py` | pass (9 tests) — start, edge, shared phase, terminal, cleanup, force, no-channels, fixed words, the human wording | the file |
| T4 | `pytest cli/tests/test_graph_*.py cli/tests/test_cleanup*.py` | pass, unmodified | existing suites |
| T5 | same file | pass — every `actor: human` node of the outer loop carries a phase or a `notify` hook | `test_every_human_node_of_the_outer_loop_is_announced` |
| T6 | `pytest cli/tests/test_lifecycle_integration.py` | pass (5 tests) — closed issue announced before the clear with state/reason/actor/kind; merged PR-as-work-item announced `merged`; a delivering PR's end silent; no publisher publishes nothing; an untracked issue silent | the file |
| T7 | `pytest cli/tests/test_channels_commands.py -k new_opens or falls_back` | pass — declared slug, prefix stripped, labels; root in `C123` with `origin: kickoff`; the reply carries the link and `the-loop start`; the answer names the link and `<#C123>` | `test_new_opens_the_work_item_and_its_thread`, `test_new_falls_back_to_kickoff_repo_without_a_prefix` |
| T8 | `pytest … -k refuses or empty_title or needs_the_create_grant or unlisted or acts_once` | pass — four kickoff refusals, the empty title, the grant, the allow-list, the trigger ring; nothing created in any | six tests (four parametrised) |
| T9 | `pytest … -k survives_a_thread` | pass — issue created, answer says the thread could not be opened, nothing bound | `test_new_survives_a_thread_that_cannot_be_opened` |
| T10 | `pytest … -k usage_and_help` | pass | `test_usage_and_help_name_the_new_verb_and_its_grant` |
| T11 | `pytest cli/tests/test_channels_declared_integration.py -k room_is_the_conversation or opened_once` | pass — one opening message, every event `thread_ts: None`, record `thread: ""` / `mode: channel`, `open` idempotent | two tests |
| T12 | `pytest … -k moves_to_the_room_as_a_room` | pass — record in the room with `origin: declared`, pointer in the old thread, old thread unmapped | `test_a_thread_declared_into_a_room_moves_to_the_room_as_a_room` |
| T13 | `pytest … -k keeps_its_shape or without_a_declaration` and the issue-375 suite | pass, existing tests unmodified | `test_a_thread_already_bound_inside_the_room_keeps_its_shape`, `test_without_a_declaration_the_central_channel_is_unchanged` |
| T14 | `pytest cli/tests/test_channels.py -k round_trips_and_is_never_a_thread` | pass — `conversation_for` / `thread_for` / no thread-map entry / a mode-less record is a thread | the test |
| T15 | `pytest … -k reply_under_a_room_message` | pass — processed, delivered to the work item | `test_a_reply_under_a_room_message_reaches_the_work_item` |
| T16 | `pytest cli/tests/test_channels.py -k lists_a_room_conversation` | pass — `(channel)` in the thread column, `mode` in the JSON | the test |
| T17 | `pytest cli/tests/test_channels.py -k provider_table` | pass — a fake beside Slack, `None` contributes nothing, a raising loader hides nothing | `test_load_channels_walks_the_provider_table` |
| T18 | `pytest cli/tests/test_graph_lifecycle.py -k registered_provider` | pass — `phase.started` reached a type the-loop does not ship, no Slack in the config | the test |
| T19 | `pytest cli/tests/test_bus.py -k skipped_message` | pass | `test_the_notify_hooks_skipped_message_names_no_channel` |
| T20 | `pytest cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py cli/tests/test_state_portability.py` | pass — the last of these **caught** the unclassified `phase` attribute during implementation | existing suites |
| T21 | — | n/a — no route changed | — |
| T22 | — | n/a — one publish per phase change, none without a `channels` section | — |
| T23 | as named in `security-review.md` | pass | see that file |
| T24 | manual, in a real Slack workspace | **not run here** — this session has no workspace, token or live work item. The automated rows cover every branch that does not need Slack itself; the one thing only a workspace shows is how a room *reads* with one message per phase, which is the operator's call to keep or narrow via `subscribe` | — |

## Gates

```text
$ uv run --project cli python -m pytest -q cli
3937 passed, 1 skipped in 165.73s

$ uv run ruff check cli hooks        → All checks passed!
$ uv run ruff format --check cli hooks → 317 files already formatted
$ uv run pyright cli                 → 0 errors, 0 warnings, 0 informations
$ uv run python scripts/validate_config.py → VALID ×5
$ npx markdownlint-cli2@0.18.1 "**/*.md"   → Linting: 1205 file(s)  Summary: 0 error(s)
```
