---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#375"
---

<!-- Authored per the the-loop:writing skill. -->

# Documentation: a work item names the room it is worked in

> The `capability-docs` node's proof, gating both sections (issue-174).

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `channels.md` | A new clause in Current behaviour: a work item can be given a room of its own — what a declaration does to the outbound thread (opened there; moved, with a pointer, when it was bound elsewhere) and to the inbound pipeline (every message no binding claims is that work item's, a top-level one included, so a declared room never opens an issue), the grammar and its per-type validation, the two cardinality rules, first-sight baselining, and the poll/socket asymmetry | yes (issue-375) |
| `webhook-triggers.md` | The keyword list gains the pair, and a new section beside the collaborator one: what a declaration records, what it does **not** grant, that declaring is an action and so is refused for anyone not named in `authorizedUsers`, the two refusal reasons, and the clear-on-close rule | yes (issue-375) |
| `cli.md` | **unaffected** — it describes the CLI's shape, not its command list; the two new verbs are documented on their own pages, which the docs-parity test pins | n/a |
| `process-graph.md` | **unaffected** — the gate gains a prose section, not a node, an edge or a decision key; nothing about the graph's shape changed | n/a |
| `instances.md` | **unaffected** — a declaration is refused out of scope exactly as any other control command is, through the same `decide_scope` call above the command branch | n/a |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/config/cli/routing-options.md` | An option entry for `control.keywords.add-channel` and `.remove-channel` — the grammar, the two consequences, the two cardinality rules, what is refused and why a Slack target is an id |
| `docs/cli/commands/add-channel.md` | New page: what the verb does, the grammar table, flags, exit codes, and the notes an operator needs (all-or-nothing, the move, poll vs socket, in-process) |
| `docs/cli/commands/remove-channel.md` | New page: the other half, and what specifically does and does not go quiet |
| `docs/cli/state.md` | The `collaborationChannels` section: the record sketch, a field table, why it is separate from `channels`, and what deleting it does |
| `skills/the-loop/reference/automation.md` | The rule as an agent reads it, beside the work-item-collaborator entry |
| `skills/the-loop/reference/collaboration.md` | One paragraph distinguishing *who may be input* from *where the conversation happens*, and that the two are declared in either order |
| `.the-loop/cli-config.yaml`, `skills/the-loop/templates/cli-config.yaml` | The two keywords, with the comment that says what a declaration is and is not |

## Not documented, deliberately

**No decision record.** The three choices worth stating — refuse a channel name rather
than add an OAuth scope, keep the declaration in a section of its own rather than in
`channels`, and make the gate's section prose rather than a checkbox — are each argued in
`design.md` §1, §1 and §5, where the code's comments point. A decision record is for a
choice later readers would otherwise re-litigate without the reasoning at hand; here the
reasoning sits next to the code that embodies it.

**No new capability doc.** A collaboration channel is not a new capability: it is the
channels capability answering "which channel?" per work item instead of per deployment.
Minting a doc for it would split one behaviour across two pages.
