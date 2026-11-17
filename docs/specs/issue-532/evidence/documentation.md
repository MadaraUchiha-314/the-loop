---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#532"
---

# Documentation: graph notifications on a gateway consumer post first time

> The `capability-docs` node's proof: both sections, same PR as the change.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`docs/capabilities/gateway.md`](../../../capabilities/gateway.md) | § The instance side, *Posting through the gateway*: graph hooks post the same way on the first attempt, because the runtime config carries `gateway` and `instance` | issue-532 row, newest |
| [`docs/capabilities/channels.md`](../../../capabilities/channels.md) | *Behind a gateway, the gateway posts*: the graph runtime's config carries both blocks, so `notify` and the lifecycle events take the gateway path first time | issue-532 row, newest |

## Documentation

| Document | What changed |
|----------|--------------|
| — | No user-facing documentation changes. No config option, command, output or workflow changed; the fix makes the documented behaviour (issue-519) hold for graph hooks too |
