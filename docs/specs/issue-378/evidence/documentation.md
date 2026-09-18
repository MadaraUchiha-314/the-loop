---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#378"
---

<!-- Authored per the the-loop:writing skill. -->

# Documentation: a work item's whole life is told to every channel, and Slack can begin one

> The `capability-docs` node's proof, gating both sections (issue-174).

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `channels.md` | Four new Current-behaviour clauses — the three lifecycle rows and the label rule, a declared room as the conversation, `/the-loop new`, the provider table; the catalog summary bullet names the three events; the observability bullet notes `mode: channel`; two design links | yes (issue-378) |
| `process-graph.md` | A Current-behaviour clause: the runtime publishes the lifecycle, following `WorkItemState.phase` | yes (issue-378) |
| `observability.md` | **unaffected** — no event-log type is added; `channel.thread_opened`'s description in `eventlog.py` gained the `mode` field, which the catalogue test reads from the code | n/a |
| `webhook-triggers.md`, `interactive-sessions.md`, `cli.md` | **unaffected** — no keyword, no spawn path, no verb shape changed | n/a |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/config/cli/channels-options.md` | Three rows in the subscribable-events table with a note that none is recorded; the `work-item.create` grant row names the slash command; a `new` row in the slash-command table; a paragraph on a declared room being the conversation |
| `docs/guide/slack.md` | Two rows in the modes table (follow the work; file from anywhere); a new *A room for one work item* section; `/the-loop new` in *Starting a work item from Slack* and in *The slash command, in full*; the grant list names `work-item.create` |
| `.the-loop/cli-config.schema.json`, `cli/the_loop/schemas/cli-config.schema.json` | The `subscribe` description lists the lifecycle events (byte-identical copies, pinned) |
| `skills/the-loop/templates/cli-config.yaml`, `.the-loop/cli-config.yaml` | The `subscribe` and `publish` comments |
| `docs/cli/state.md` | `phase` in the work-item-state attribute table; `mode` in the portable record's `channels` section |
| `skills/the-loop/reference/collaboration.md` | The channel paragraph names the lifecycle events |
| `docs/decisions/decision-130.md` + index | The two design choices and the provider row |
| `README.md`, `docs/guide/*` (other pages) | **unchanged, deliberately** — the front page describes the loop, not the channel catalog; the Slack guide is the one page a Slack operator meets first and it is updated |
