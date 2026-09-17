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
| T20 | manual, in a real Slack workspace | **not run here** — this session has no workspace, token or live work item. It is the one row of the plan that is an operator's to run; the automated rows cover every branch that does not need Slack itself. Since the review it also covers the **re-install**: the three new scopes reach an existing app only when it is re-installed from the updated manifest | — |

## Round 2 — names instead of ids (the author's review of PR #376)

| # | Command | Outcome | Artifact |
|---|---|---|---|
| T21 | `pytest cli/tests/test_channels_directory.py` | pass — an id costs no call; a name costs one and is cached; a miss on a fresh map does not re-read; a stale map refreshes on a miss; the two maps survive each other | `test_an_id_is_returned_without_a_lookup`, `test_a_name_is_resolved_once_and_then_cached`, `test_a_miss_on_a_fresh_map_does_not_re_read`, `test_a_stale_map_is_refreshed_on_a_miss`, `test_the_two_maps_do_not_clobber_each_other` |
| T22 | `pytest cli/tests/test_channels_directory.py -k fail or handle or display` | pass — a failing read, no token and an unreadable cache each resolve to `""`; a deleted member resolves to nobody; **only the handle resolves**; a moved handle is warned about | `test_a_failing_read_resolves_to_nothing`, `test_only_the_handle_resolves_never_the_display_name`, `test_a_handle_that_moved_is_warned_about` |
| T23 | `pytest cli/tests/test_workchannels_integration.py` | pass — `slack@#tmp-issue-375` stores `slack@C0TMP375` with `name="tmp-issue-375"` and `label="slack@#tmp-issue-375"`; `#ghost` is refused 😕 with nothing written | `test_a_channel_name_is_resolved_to_its_id`, `test_a_name_that_resolves_to_nothing_is_refused` |
| T24 | `pytest cli/tests/test_channels_declared_integration.py -k central or id_still` | pass — `channel: "#the-loop"` posts into `C123`; `#gone` raises naming what to check; an id drives a whole post with no directory at all | `test_the_central_channel_may_be_declared_by_name`, `test_a_central_channel_name_that_resolves_to_nothing_refuses`, `test_an_id_still_needs_no_directory_at_all` |
| T25 | `pytest cli/tests/test_channels_declared_integration.py -k allow_list or handle` | pass — the handle `dana` authorizes `U0DANA`; `ghost` authorizes nobody | `test_an_allow_list_handle_authorizes_its_member`, `test_an_unresolvable_handle_authorizes_nobody` |
| T26 | `pytest cli/tests/test_channels*.py cli/tests/test_standing_channels_integration.py` | pass, unmodified — including the two fixtures whose "ids" are `C9` and `C-OPS`, which is what forced the id rule to be about **case** rather than shape | existing suites |

The issue-375 files and the suites they extend now run **199 tests**.

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

1. **T20 is unrun, and it now matters more.** Everything below Slack's API boundary is
   proved, including every branch of the resolver against a fake `conversations.list` /
   `users.list`. What is *not* proved is that the real methods answer the shape the
   resolver reads and that the three scopes are sufficient — that needs a workspace and a
   re-installed app. The failure mode is loud: a name resolves to nothing, the log names
   the probably-missing scope, and the declaration or the post is refused rather than
   going somewhere unexpected.
2. **Poll mode sees less than Socket Mode** (`design.md` §4). Tested as designed, not as
   an operator might assume: a reply in a thread the-loop did not open, in a declared
   room, is delivered under `socket` and not under `poll`.
