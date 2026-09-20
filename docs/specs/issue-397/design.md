---
type: design
phase: design
workItem: "github:MadaraUchiha-314/the-loop#397"
status: approved
approvedBy: ["the-loop"]     # locked with testing-plan.md; tier 2
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Design: minor Slack polish — room-declaration confirmation, ephemeral help, connector signature

> Phase 2 of 4. Derives from the approved [`requirements.md`](requirements.md).

## Overview

**Nothing new is built; two existing seams are called from one more place each.**

- **R1** reuses the **conversation opener** (issue-317): the dispatcher already holds
  one (`Dispatcher.opener`, injected by the daemons over their config getter) and calls
  it the moment a start is accepted. `_apply_channel` now calls it once more, right
  after a *new* declaration is written, through a small `_confirm_room` that swallows
  every failure. The CLI verb (`core.workchannels.manage_channels`) does the same
  through `bus.open_conversation` when the config has a `channels` section, and reports
  the outcome as one more line of its output.
- **R2/R3** reuse the verb parser: `parse_verb` already hands `help` its remainder;
  `wants_public_help(verb)` reads the first token of the remainder's first line, and
  `process_reply` answers with `bot.say` (an ordinary reply in the member's thread)
  instead of `_tell` (the ephemeral).

```mermaid
flowchart LR
  subgraph declare ["a room is declared (R1)"]
    GH["ticket comment<br/>the-loop add-channel"] --> DISP["Dispatcher._apply_channel"]
    CLI["the-loop add-channel (CLI)"] --> CORE["core.workchannels.manage_channels"]
    DISP -->|"changed"| CR["_confirm_room → self.opener"]
    CORE -->|"applied"| CR2["_confirm_room → bus.open_conversation"]
    CR --> OPEN["SlackBotChannel.open<br/>(idempotent: room already bound ⇒ nothing)"]
    CR2 --> OPEN
    OPEN --> ROOM["room: 'every update about … is posted here'"]
  end
  subgraph help ["help (R2, R3)"]
    M["@the-loop help [public]<br/>(+ optional 2nd-line signature)"] --> PV["parse_verb → Verb('help', rest)"]
    PV --> W["wants_public_help: first token of rest's FIRST line == 'public'"]
    W -->|"yes"| SAY["bot.say — visible reply in the thread"]
    W -->|"no"| EPH["_tell — chat.postEphemeral (as before)"]
  end
```

## Why the opener, not a new message (R1)

The ticket offered two shapes: the existing room-opened message at declaration, or a
new one-liner. The existing message is the right one: it *is* the "this room is the
conversation" statement, it binds the record (`mode: channel`) so the first update is
delivered as a room message rather than opening the room then, and the open is
idempotent by the channel's contract — so declaring, starting and re-declaring in any
order produce exactly one message. A conversation already bound in the central channel
moves at the declaration instead of at the next event, which is issue-375 R2.2's move
brought forward; the pointer left behind is unchanged.

## Error handling

| Where | Failure | Behaviour |
|---|---|---|
| dispatcher | `opener` is `None` (tests, embedders) | nothing opened; declaration and 🎉 as before |
| dispatcher | opener raises | `logger.exception`, declaration stands, comment settled as executed |
| CLI | no `channels` section | nothing opened |
| CLI | bus returns a failed `PostResult` | one `err` line naming the channel and the error; exit code unchanged |
| inbound | `help public` from a member who may not speak | refused by the unchanged speaker check before this branch |

## Data & config

No config key, grant, scope, schema, state file or event type changes. One new public
name in `channels.verbs` (`wants_public_help`, `PUBLIC_HELP`), one private method on
the dispatcher, one private function in `core.workchannels`.
