---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#375"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: a work item names the room it is worked in

> The last spec artifact (requirements → design → testing plan → tasks). A DAG of
> implementation tasks derived from the approved design and testing plan.

## Task list

- [x] 1. The grammar and the store
  - `cli/the_loop/workchannels.py`: `ChannelRef`, `CHANNEL_TYPES` with the Slack target
    validator, `parse_channel_ref` / `parse_channel_refs` / `describe_refusal`,
    `CollaborationChannel`, `ChannelTakenError` and `CollaborationChannelStore`
    (`list`, `for_type`, `declared_by`, `targets`, `add`, `remove`, `clear`)
  - `cli/the_loop/workitem.py`: the `collaborationChannels` section constant, in
    `SECTIONS` and in the module's record sketch
  - _Depends on:_ none
  - _Requirements:_ R1.1–R1.7, R3.4
  - _Test:_ T1, T2, T3 (red→green)

- [x] 2. The section travels with the work item's life cycle
  - `cli/the_loop/state.py`: an `ATTRIBUTES` entry classifying it as an operator ledger
  - `cli/the_loop/reset.py`: the section in `PIECES` and in both clearing lists
  - `cli/the_loop/poller/poller.py`: the section in the tracked-item scan
  - `docs/cli/state.md`: the section's own heading, fields and deletion note
  - _Depends on:_ 1
  - _Requirements:_ R1.10, R5.2
  - _Test:_ T16, T17

- [x] 3. The control vocabulary
  - `cli/the_loop/control.py`: `ADD_CHANNEL` / `REMOVE_CHANNEL`, `CHANNEL_COMMANDS`,
    `ARGUMENT_COMMANDS`, the per-command argument parser in `parse_command`, and
    `command_comment` spelling a channel without the `@` prefix
  - _Depends on:_ 1
  - _Requirements:_ R1.1, R1.3
  - _Test:_ T12 (red→green)

- [x] 4. The dispatcher applies it
  - `cli/the_loop/webhook/dispatcher.py`: `channel_store`, the `CHANNEL_COMMANDS` branch,
    `_apply_channel` (refusing `missing-channel` / `channel-taken`, settling
    `control-executed`), and clearing the section when the work item ends
  - _Depends on:_ 3
  - _Requirements:_ R1.1, R1.2, R1.4–R1.7, R1.10, R3.4
  - _Test:_ T13, T14 (red→green)

- [x] 5. The CLI verbs
  - `cli/the_loop/core/workchannels.py`: `manage_channels` / `list_channels`, validate-all
    then apply, the keyword posted back best-effort
  - `cli/the_loop/commands/workchannels_cmd.py` + `commands/__init__.py`: `add-channel`
    and `remove-channel`
  - _Depends on:_ 3
  - _Requirements:_ R1.9
  - _Test:_ T4 (red→green)

- [x] 6. Outbound: the conversation lives in the declared room
  - `cli/the_loop/channels/state.py`: `ChannelStores.declared` / `declared_work_item` /
    `declared_targets`, and `declared` in `CONVERSATION_ORIGINS`
  - `cli/the_loop/channels/slack.py`: `home_for`, `_no_channel`, `_conversation`,
    `_say_moved`, `_open_thread(channel_id=…)`, and `post` / `open` routed through them
  - _Depends on:_ 1
  - _Requirements:_ R2.1–R2.4
  - _Test:_ T5, T6, T11 (red→green)

- [x] 7. Inbound: every message in the room is about the work item
  - `cli/the_loop/channels/slack.py`: `fetch_channel_messages` with first-sight
    baselining, and `fetch_kickoffs` standing down in a declared channel
  - `cli/the_loop/channels/inbound.py`: the room lookup before the kickoff branch, the
    binding-wins order, the room cursor for a message that is its own root, and the
    declared-channel loop in `poll_once`
  - _Depends on:_ 6
  - _Requirements:_ R3.1–R3.3, R3.5, R3.6
  - _Test:_ T7, T8, T9, T10, T11 (red→green)

- [x] 8. The gate asks the question
  - `cli/the_loop/graph/bootstrap.py`: seed `portableDir`
  - `cli/the_loop/graph/hooks/selection.py`: `_declared_channels`, `_channel_lines` in the
    checklist, and the confirmation's channel line
  - _Depends on:_ 1
  - _Requirements:_ R4.1–R4.3
  - _Test:_ T15 (red→green)

- [x] 9. Configuration and its documentation
  - `.the-loop/cli-config.schema.json` + the packaged copy: the two keyword entries
  - `.the-loop/cli-config.yaml`, `skills/the-loop/templates/cli-config.yaml`: the keywords
    with the comment that says what a declaration is and is not
  - `docs/config/cli/routing-options.md`: an option entry for each
  - `docs/cli/commands/add-channel.md`, `remove-channel.md`
  - _Depends on:_ 3, 5
  - _Requirements:_ R5.2
  - _Test:_ T17

- [x] 10. Capability and skill documentation
  - `docs/capabilities/channels.md`, `docs/capabilities/webhook-triggers.md`: current
    behaviour plus a history row
  - `skills/the-loop/reference/collaboration.md`, `reference/automation.md`: the rule as
    an agent reads it
  - `evidence/documentation.md`: what changed and why
  - _Depends on:_ 9
  - _Requirements:_ R5.1
  - _Test:_ T17

- [x] 11. Verification
  - the full suite, `make check`, and the evidence files
  - _Depends on:_ 1–10
  - _Requirements:_ all
  - _Test:_ T1–T17
