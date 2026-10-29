---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#529"
---

# Documentation: a Slack kickoff offers Do or Start

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [channels.md](../../../capabilities/channels.md) | The rendering bullet names **Do** and **Start** on the kickoff's "opened" reply. A new bullet, *A new work item is offered both loops*, states the behaviour in EARS: every kickoff path, the order, the description lines, the press, the issue created before the choice. The `/the-loop new` bullet names both buttons | `issue-529` |

## Documentation

| Document | What changed |
|----------|--------------|
| [README.md](../../../../README.md) | The `channels listen` line lists Do among the buttons |
| [guide/slack.md](../../../guide/slack.md) | The kickoff section explains choosing Do or Start, typed or pressed. The button table has a Do / Start row with what each stands for. The architecture diagram, the manifest comment, `/the-loop new` and the sample `channels status` output name Do |
| [guide/gateway.md](../../../guide/gateway.md) | The buttons that work through a gateway include Do |
| [config/cli/channels-options.md](../../../config/cli/channels-options.md) | The `control.command` grant row, the read-mode note and `/the-loop new` name the Do button |
| [cli/commands/channels.md](../../../cli/commands/channels.md) | `channels status`'s button line reads `Execute / Do / Start` |
| [skills/the-loop/reference/collaboration.md](../../../../skills/the-loop/reference/collaboration.md) | The channel-rendering sentence names Do / Start on a kickoff's reply |
