---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# Documentation: Introducing the-loop gateway

> The `capability-docs` node's proof, and it gates **both** sections (issue-174). A work
> item that genuinely changed nothing in either says so **with the reason** — "internal
> refactor, no described behaviour changed" is an answer; a blank is not. A row names a
> **document**, never a token, a credential or an internal hostname: this tree is as
> public as the repository.

## Capability docs

> The ORGANIZED VIEW OF SPECS — current behaviour per capability, for a reader who
> already uses the project. Updated in the **same PR** as the change.

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `docs/capabilities/gateway.md` | New capability: the process and its verbs, the transports, subjects/queues/consumers, the instance side (as amended: receiver and poller stay, listener off, gateway polling opt-in), observability, what it does not do, the review rounds' rules (first-sight baseline, peer fingerprint, bindings named and recorded, the bounds) | issue-496 |
| `docs/capabilities/capabilities.md` | Index row for the gateway | — |
| `docs/capabilities/instances.md` | An instance with a `gateway` block polls its queue under `instance.name` beside its own receiver and poller; claims, actors, the Gateway card | issue-496 |
| `docs/capabilities/channels.md` | Slack behind a gateway: Socket Mode only, the mention rule, one connection per app held by the gateway; bound threads publish bindings | issue-496 |
| `docs/capabilities/cli.md` | The `gateway` verb family | issue-496 |
| `docs/capabilities/control-plane.md` | `GET /api/v1/gateway` and the Gateway card | issue-496 |
| `docs/capabilities/observability.md` | The `gateway.*` and `subject.*` event families | issue-496 |
| `docs/capabilities/webhook-triggers.md` | A webhook re-pointed at the gateway, the instance's receiver beside it | issue-496 |

## Documentation

> The USER-FACING surface — README, the docs site, the operating-model skill — for a
> reader who does not yet. It rots the same way, so it is updated in the same PR.

| Document | What changed |
|----------|--------------|
| `docs/guide/gateway.md` (new, in the docs nav) | Moving to a gateway: when you want one, the six steps, what does not change, who polls |
| `docs/guide/slack.md` | Several instances on one app: run one gateway per app; link to the move |
| `docs/cli/commands/gateway.md` (new) and `docs/cli/commands/index.md` | The `gateway start\|stop\|restart\|status\|subjects\|instances` verbs |
| `docs/config/cli/gateway-options.md` (new) | The instance's `gateway` block, option by option, as amended |
| `docs/cli/commands/upgrade.md` | Neither upgrade verb moves an instance behind a gateway; link to the guide |
| `docs/api-specs/openapi/the-loop-gateway.v1.yaml` (new) and `the-loop.v1.yaml` | The gateway's contract (fetch, commit, claims, actors, bindings with instance and peer, views) and the instance's `GET /api/v1/gateway` |
| `docs/decisions/decision-144.md`, `-145.md`, `-146.md`, `decisions.md` | The name, the queue contract, no instance auth in the first landing |
| `docs/learnings/learning-010.md` … `learning-016.md`, `learnings.md` | Seven learnings from the build and the live proof (a ClassVar hook bound as a method; a graceful stop must release long-polls; …) |
| `commands/init.md`, `commands/upgrade-the-loop.md` | Init asks about a gateway and scaffolds `gateway-config.yaml`; upgrade reports the shape a gateway replaces under needs-user and never writes a block |
| `skills/the-loop/templates/gateway-config.yaml` (new), `skills/the-loop/reference/onboarding.md` | The gateway config template (polling off by default) and the onboarding note |
| `cli/the_loop/schemas/gateway-config.schema.json` (new), `cli-config.schema.json`, and their `.the-loop/` copies | The fourth schema; the `gateway` block |
| `docs/.vitepress/config.mts` | Nav entries for the guide page and the new command/options pages |
