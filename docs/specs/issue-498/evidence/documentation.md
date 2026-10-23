---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#498"
---

# Documentation: a control keyword must open the comment; an ambiguous body is conversation

> The `capability-docs` node's proof (issue-174): both sections, same PR as the change.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`docs/capabilities/webhook-triggers.md`](../../../capabilities/webhook-triggers.md) | The keyword EARS bullet now states the leading-keyword rule and that an ambiguous comment executes neither command and is routed as conversation | issue-498 row, newest |
| [`docs/capabilities/channels.md`](../../../capabilities/channels.md) | The ledger-record bullet: a relay puts the person's words first and the attribution after | issue-498 row, newest |
| [`docs/capabilities/process-graph.md`](../../../capabilities/process-graph.md) | The phase-selection bullet: the reply is read with the control grammar and must open with the execute keyword; a checklist in the reply goes below it | issue-498 row, newest |

## Documentation

| Document | What changed |
|----------|--------------|
| [`docs/config/cli/routing-options.md`](../../../config/cli/routing-options.md) | The keyword-matching paragraph: opens-the-comment rule, ambiguous → conversation |
| `cli/the_loop/schemas/cli-config.schema.json` and `.the-loop/cli-config.schema.json` | `routing.control.keywords` description, same rule |
| The phase-selection checklist comment (`selection.py`) | "Start your reply with `the-loop execute`"; the reply's checklist goes below the keyword |
| [`docs/learnings/learning-018.md`](../../../learnings/learning-018.md), `learning-011.md`, index | The learning, and learning-011's action updated to what shipped |
