<!-- Authored per the the-loop:writing skill. -->

# Decision 130: a work item's lifecycle is published by the runtime, and a declared room is the conversation

- **Status:** proposed
- **Date:** 2026-09-18
- **Deciders:** the-loop (architect, engineer), asked for by @MadaraUchiha-314
- **Work item:** [issue-378](https://github.com/MadaraUchiha-314/the-loop/issues/378)
- **Builds on:** [decision-103](decision-103.md) (every channel is a peer on one bus),
  [decision-105](decision-105.md) (one thread per work item, rooted on the work item),
  [decision-107](decision-107.md) (the conversation opens on the spawn path) and
  issue-375 (a work item names the room it is worked in).

## Context

[Issue #378](https://github.com/MadaraUchiha-314/the-loop/issues/378) asks for a work item
managed end to end from Slack and names the symptom: *"slack channel getting an event is a
hit or a miss."* The bus delivers everything published onto it; what is published is the
ask, the comment mirror and the `notify` hook — and the hook fires only where a graph
author wrote it on a node. A phase starting or ending is a line in the machine's event log
and nothing else, and a work item closed on GitHub reaches no channel at all.

Two questions had more than one defensible answer.

## Decision

**1. The lifecycle is the runtime's to publish, not a hook's to remember.** The runtime
already emits `graph.started`, `graph.advanced` and `graph.cleaned` for every transition of
every graph; `phase.started`, `phase.completed` and `work-item.closed` are published beside
them, by the runtime and the dispatcher, as catalog rows any channel may subscribe to.
They follow the **label**: a transition between two nodes that share a phase publishes
nothing, a node without a phase inherits the phase before it, and a force — which sets no
label — publishes nothing. They are **not recorded** on the ledger: the label is the
ledger's record of the phase, and the closure is its own record.

**2. A declared room is channel-based; the central channel stays thread-based.** A room
declared on a work item (issue-375) exists for that one work item, so the-loop's updates
there are top-level messages and the room *is* the conversation (`mode: channel`, no
thread). The central channel is shared by every work item, so its threads stay. The
declaration decides the mode; there is no flag.

**3. The next channel type is a row.** `load_channels` walks a provider table instead of
naming Slack; the publishers speak `Event` and nothing else.

## Consequences

- Every shipped graph and every custom graph fires the lifecycle without a YAML change.
- A channel that subscribes to nothing new sees nothing new; no config version bump.
- A phase a cleanup interrupts never "completes"; the channel sees `phase.started(cleanup)`
  or `work-item.closed`, which is the truth.
- A room is louder than a thread — one message per event in the channel — by the
  operator's choice in declaring it. A conversation already bound as a thread inside a room
  keeps its shape; re-declaring the room re-opens it as a room.
- A threaded room, if anyone wants one, is a later `mode` on `add-channel`.

## Alternatives considered

- **A `notify` hook on every node** — five graphs, every node, and a rule a custom graph
  would have to know. Rejected.
- **Node-level events** — the review chain alone is six nodes with no phase; a person
  follows the label, so the events follow the label. Rejected.
- **Record the transitions as ticket comments** — noise the ledger's ingress then has to
  classify and drop. Rejected.
- **A per-declaration thread/channel flag** — a branch nobody has asked for and nobody
  would test. Deferred.
- **An ephemeral repository picker for `/the-loop new`** — the picker's outcome is written
  onto the question message, which an ephemeral message cannot be. The `<repo>:` prefix
  answers it. Deferred.
