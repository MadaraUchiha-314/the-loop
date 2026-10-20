---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#507"
---

# Documentation: answer a Slack mention in the thread it came from

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [channels](../../../capabilities/channels.md) | New bullet after the issue-378 room rule: a mention in a thread sets the work item's reply thread, the next `comment.agent` is posted there, any non-progress event clears it; it names itself as the one exception to "every room event is top-level" | issue-507 row added |

## Documentation

| Document | What changed |
|----------|--------------|
| [docs/guide/slack.md](../../../guide/slack.md#a-room-for-one-work-item) | "A room for one work item": a mention inside a thread is answered in that thread, until the room hears a new conversation; a top-level mention is answered at the top level; no verb binds a thread by hand (the ticket's open question) |

`README.md` and the skill's `reference/` docs say nothing about where Slack answers land,
so neither changed.
