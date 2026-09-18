---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#378"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: a work item's whole life is told to every channel, and Slack can begin one

> The last spec artifact (requirements → design → testing plan → tasks). A DAG of
> implementation tasks derived from the approved design and testing plan.

## Task list

- [x] 1. The catalog rows and the publisher
  - `cli/the_loop/channels/events.py`: `phase.started`, `phase.completed`,
    `work-item.closed`; `LIFECYCLE_EVENTS`
  - `cli/the_loop/channels/publishers.py`: `publish_lifecycle`, `lifecycle_publisher`,
    the `Lifecycle` callable type
  - `cli/the_loop/graph/hooks/sideeffects.py`: the neutral skipped message
  - _Depends on:_ none
  - _Requirements:_ R1.6, R1.7, R3.4, R6.1, R6.4
  - _Test:_ T1, T2, T19 (red→green)

- [x] 2. The runtime publishes the lifecycle
  - `cli/the_loop/graph/runtime.py`: `phase_of`, `_lifecycle`, the calls in `start`,
    `advance` (edge and terminal) and `cleanup`
  - `cli/tests/test_graph_lifecycle.py`: T3, T5, T18
  - _Depends on:_ 1
  - _Requirements:_ R1.1–R1.5, R1.8, R2.1, R2.2
  - _Test:_ T3, T4, T5 (red→green)

- [x] 3. The dispatcher announces the close
  - `cli/the_loop/webhook/dispatcher.py`: the `lifecycle` parameter, `_announce_closed`
    above the clears in `_record_closure`
  - `cli/the_loop/poller/daemon.py`, `cli/the_loop/webhook/daemon.py`,
    `cli/the_loop/core/daemons.py` (if it builds one): wire `lifecycle_publisher(getter)`
  - `cli/tests/test_lifecycle_integration.py`: T6
  - _Depends on:_ 1
  - _Requirements:_ R3.1–R3.5
  - _Test:_ T6 (red→green)

- [x] 4. The provider table
  - `cli/the_loop/channels/base.py`: `Loader`, `CHANNEL_PROVIDERS`, `_load_slack`,
    `load_channels` walking the table
  - _Depends on:_ none
  - _Requirements:_ R6.2, R6.3
  - _Test:_ T17 (red→green), T18

- [x] 5. The room conversation
  - `cli/the_loop/channels/state.py`: `mode` in `_record`, `conversation_for`,
    `bindings()` accepting a room, `_with_bindings` registering threads only
  - `cli/the_loop/channels/slack.py`: `_conversation` opening a room for a declared home,
    `_open_room`, `render_room`, `post` / `open` reading `conversation_for` and passing
    `thread_ts=… or None`
  - `cli/the_loop/commands/channels_cmd.py`: the mode column in `threads`
  - _Depends on:_ none
  - _Requirements:_ R5.1–R5.7
  - _Test:_ T11–T16 (red→green)

- [x] 6. `/the-loop new`
  - `cli/the_loop/channels/commands.py`: the `create` family in `parse_invocation`,
    `FAMILY_GRANTS`, `usage()`, `_create_verb`, the `create_issue` / `client_factory` seams
  - _Depends on:_ 5 (opens the conversation through the same `open`)
  - _Requirements:_ R4.1–R4.6
  - _Test:_ T7–T10 (red→green)

- [x] 7. Documentation
  - `docs/config/cli/channels-options.md`: three catalog rows; the `new` verb under the
    slash command and the `work-item.create` grant row
  - `.the-loop/cli-config.schema.json` + `cli/the_loop/schemas/cli-config.schema.json`:
    the `subscribe` description
  - `skills/the-loop/templates/cli-config.yaml`, `.the-loop/cli-config.yaml`: the comment
  - `docs/capabilities/channels.md`: three Current-behaviour clauses, design links, history
  - `docs/capabilities/process-graph.md`: the runtime publishes the lifecycle
  - `docs/guide/slack.md`: modes table, the slash command in full, starting a work item,
    the room
  - `docs/decisions/decision-130.md` + index
  - _Depends on:_ 1–6
  - _Requirements:_ R7.1–R7.4
  - _Test:_ T20

- [x] 8. Evidence and the gates
  - `evidence/self-review.md`, `critic-review.md`, `security-review.md`,
    `final-validation.md`, `documentation.md`, `pull-requests.md`; `make check`
  - _Depends on:_ 7
  - _Requirements:_ all
  - _Test:_ T4, T20, T23, T24
