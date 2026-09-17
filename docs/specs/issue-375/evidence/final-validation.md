---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#375"
---

<!-- Authored per the the-loop:writing skill. -->

# Final validation: a work item names the room it is worked in

> The `verification` node's proof: every activity in `testing-plan.md` ticked, with the
> command, the outcome and the committed artifact.

## Results

| # | Command | Outcome | Artifact |
|---|---|---|---|
| T1 | `pytest cli/tests/test_workchannels.py -k grammar or canonicalised or refused` | pass — both spellings canonicalise; a name, an unknown type, a lower-case id, a path fragment and an argv fragment each refused with a reason | `test_a_channel_ref_is_canonicalised`, `test_anything_else_is_refused_not_repaired`, `test_a_run_of_refs_stops_at_the_first_token_that_is_not_one` |
| T2 | `pytest cli/tests/test_workchannels.py` | pass — provenance recorded; a second channel of one type replaces and reports; a held channel raises; remove and clear | `test_a_declaration_is_recorded_with_its_provenance`, `test_a_second_channel_of_one_type_moves_the_conversation`, `test_a_channel_another_work_item_holds_is_refused`, `test_removing_and_clearing` |
| T3 | `pytest cli/tests/test_workchannels.py -k lookup or contested or unreadable` | pass — a room names its work item; a contested room names nobody; an unreadable entry declares nothing | `test_the_room_names_its_work_item`, `test_a_contested_room_is_attributed_to_nobody`, `test_an_unreadable_entry_declares_nothing` |
| T4 | `pytest cli/tests/test_workchannels_cli.py` | pass (13 tests) — the posted keyword re-parses to the same command and is self-marked; every refusal exits 2 having written and posted nothing | `test_add_declares_and_records_it_on_the_ticket` and the rest of the file |
| T5 | `pytest cli/tests/test_channels_declared_integration.py -k thread_root or open_uses` | pass — root and reply both land in the declared room; the binding records it; `open` resolves the same home | `test_the_thread_root_is_opened_in_the_declared_channel`, `test_open_uses_the_declared_room_too` |
| T6 | `pytest … -k declaration_after` | pass — root in the new room, `origin: declared`, pointer in the thread it left, old thread unmapped | `test_a_declaration_after_the_conversation_started_moves_it` |
| T7 | `pytest … -k top_level or central_channel` | pass — recorded on the work item and delivered, nothing created; the same when the declared room **is** the central channel | `test_a_top_level_message_in_the_room_is_a_reply_on_the_work_item`, `test_declaring_the_central_channel_stops_it_opening_work_items` |
| T8 | `pytest … -k unbound_thread or bound_thread or unauthorized or undeclared` | pass — unbound thread reaches the item, a bound thread wins, an unauthorized member is dropped, an undeclared room is `unmapped`, a removed declaration goes quiet | four tests in the same file |
| T9 | `pytest … -k baselines` | pass — first cycle delivers nothing, second delivers the new message | `test_the_poll_read_baselines_a_room_before_delivering_anything` |
| T10 | `pytest … -k processes_a_room_message_once` | pass — three cycles, one delivery | `test_the_poll_read_processes_a_room_message_once` |
| T11 | `pytest cli/tests/test_channels.py cli/tests/test_channels_kickoff*.py` plus the two regression tests | pass, existing suites unmodified except one refusal-message assertion updated with its reason | `test_without_a_declaration_the_central_channel_is_unchanged`, `test_the_central_channel_still_opens_work_items` |
| T12 | `pytest cli/tests/test_control.py` | pass (67 tests) — the keywords are declared like every other, carry the channel, match as whole tokens, put nothing but a channel in `subjects`, and the paper trail spells a channel without an `@` | the issue-375 block at the end of the file |
| T13 | `pytest cli/tests/test_workchannels_integration.py` | pass (9 tests) — declared and 🎉; name, unknown type and held channel each refused 😕 with nothing written; unauthorized author declares nothing; two keywords declare nothing | the whole file |
| T14 | `pytest … -k neither_arms_nor_spawns` | pass — no spawn, no delivery, no control record | `test_declaring_neither_arms_nor_spawns` |
| T15 | `pytest cli/tests/test_selection_choices.py` | pass (26 tests) — the section names what is declared or how to declare one, carries no checkbox, and the confirmation speaks in both directions | the issue-375 block at the end of the file |
| T16 | `pytest cli/tests/test_state_portability.py cli/tests/test_reset.py` | pass — the section is classified, documented, cleared by `reset` and seen by the poller's scan. This gate **caught** the missing `ATTRIBUTES` entry during implementation | existing suites |
| T17 | `pytest cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py` | pass — both commands have a page, both keywords an option entry, the schema copies byte-identical | existing suites |
| T18 | — | n/a — one directory read per outbound post and per inbound message, over files the bindings already come from; no path gained a network call | — |
| T19 | — | n/a — no control-plane route added (decision-102's in-process class) | — |
| T20 | manual, in a real Slack workspace | **not run here** — this session has no workspace, token or live work item. It is the one row of the plan that is an operator's to run; the automated rows cover every branch that does not need Slack itself | — |

## Gates

```text
uv run ruff check cli hooks          → All checks passed!
uv run ruff format cli hooks         → 6 files reformatted, 307 unchanged (then clean)
uv run pyright cli                   → 0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py → VALID ×6
markdownlint-cli2 (changed files)    → 0 error(s)
uv run --project cli pytest -q cli   → 3842 passed, 1 skipped
```

The issue-375 files alone: 161 tests across `test_workchannels.py`,
`test_workchannels_cli.py`, `test_workchannels_integration.py`,
`test_channels_declared_integration.py`, `test_selection_choices.py` and
`test_control.py`.

## What a reviewer should distrust

1. **T20 is unrun.** Everything below Slack's API boundary is proved; that the bot can
   actually post in a room an operator declared is not, because it needs a workspace.
   The failure mode is loud (a `ChannelError` reported like any other post failure) and
   the likely cause is mundane — the bot has not been invited to the channel.
2. **Poll mode sees less than Socket Mode** (`design.md` §4). Tested as designed, not as
   an operator might assume: a reply in a thread the-loop did not open, in a declared
   room, is delivered under `socket` and not under `poll`.
