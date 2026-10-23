---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#519"
---

# Documentation: outbound Slack through the gateway, and a loud failure when it cannot

> The `capability-docs` node's proof (issue-174): both sections, same PR as the change.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`docs/capabilities/gateway.md`](../../../capabilities/gateway.md) | The opening boundary statement now says the gateway posts to Slack for its instances with the token it already held; "holds no posting token" became "no GitHub or Jira posting token"; a new § Outbound Slack (the two routes, the three checks, the stated posture, health); two bullets under § The instance side (posting through the gateway, the loud failure); § What it does not do names posting among what an exposed gateway permits | issue-519 row, newest |
| [`docs/capabilities/channels.md`](../../../capabilities/channels.md) | A new behaviour bullet, *Behind a gateway, the gateway posts*: the one resolver, the call sites, the failure semantics, and the EARS of what `start`, `status`, `channels status` and `doctor slack` say | issue-519 row, newest |

## Documentation

| Document | What changed |
|----------|--------------|
| [`docs/guide/gateway.md`](../../../guide/gateway.md) | Step 1: the gateway spawns nothing and holds no GitHub or Jira posting token, and with the bot token it holds it posts to Slack for the instances (`slack.post.enabled`, on by default) |
| [`docs/config/cli/gateway-options.md`](../../../config/cli/gateway-options.md) | New § Outbound Slack: own token first, else through the gateway, the failure semantics, the `status` and `start` wording |
| [`docs/config/cli/channels-options.md`](../../../config/cli/channels-options.md) | `slack.botTokenEnv`: optional behind a posting gateway, used first when set |
| [`docs/cli/commands/gateway.md`](../../../cli/commands/gateway.md) | `status` output gains `slack posting:` |
| `commands/init-cli.md` | The bot-token step says the token is optional on an instance behind a posting gateway and what `start` says without it |
| `commands/init-gateway.md` | The `slack` block's walk asks `slack.post.enabled` once, default on, with what each value means |
| `skills/the-loop/reference/onboarding.md` | The gateway-consumer paragraph: the bot token is optional when the gateway posts |
| [`docs/api-specs/openapi/the-loop-gateway.v1.yaml`](../../../api-specs/openapi/the-loop-gateway.v1.yaml) | The two operations, their bodies and every error body; the description names posting as the bot among what an exposed gateway permits |
| [`docs/decisions/decision-151.md`](../../../decisions/decision-151.md), [`decision-146.md`](../../../decisions/decision-146.md), `decisions.md` | The new decision record; decision-146 points at its amendment; the index row |
| `README.md`, `skills/the-loop/SKILL.md` | Unchanged: neither describes where the Slack bot token lives; the operating model did not change |
