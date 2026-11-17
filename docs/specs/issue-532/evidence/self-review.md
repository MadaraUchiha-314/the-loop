---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#532"
---

# Self-review: graph notifications on a gateway consumer post first time

> The `self-review` node's proof. Policy (`the-loop critic policy`): two self rounds,
> stop on zero new findings, escalate on a repeated finding.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | claude/opus-5.5 | new findings (1, no defect) | 1 every other reader of `gateway` / `instance` (`core/lifecycle`, `channels/watcher`, `api/ingress`, `gateway/client`, `commands/channels_cmd`, `slack.SlackChannelConfig.from_mapping`) already gets the full loaded CLI config, and only `notify` and `publish_lifecycle` publish from the runtime config → no change; noted that `from_mapping`'s false `read.mode is 'gateway' but no usable gateway` ERROR, logged whenever a graph runtime loaded the channels, also goes away with this fix | PR #534 |
| 2 | claude/opus-5.5 | zero (converged) | none — re-checked `None` vs absent `gateway` (`gateway_block` treats both as no block), `instance: {}` → default name, and that neither key carries a secret | PR #534 |
