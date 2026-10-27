---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#524"
---

# Documentation: a review session receives the CI heal prompt

> The `capability-docs` node's proof: both sections, same PR as the change.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`docs/capabilities/webhook-triggers.md`](../../../capabilities/webhook-triggers.md) | New EARS bullet: the CI gate drops a CI event for a review-loop session (`ci-review-loop`), judges the event against the authoring sessions alone, and with none left settles it without spending an attempt. A paused or resumed reviewer stays a reviewer | issue-524 row, newest |
| [`docs/capabilities/process-graph.md`](../../../capabilities/process-graph.md) | New bullet under loop selection: a `pause`/`resume` control record keeps `armedBy` and `loop` | issue-524 row, newest |

## Documentation

`docs/config/cli/routing-options.md` § CI says that a `the-loop review` session never
receives a CI event through the gate, and names the drop reason. The event catalogue
(`cli/the_loop/eventlog.py`) lists `ci-review-loop` under `dispatch.dropped` and
`poll.comment_settled`.
