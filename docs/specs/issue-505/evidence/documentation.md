---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#505"
---

# Documentation: the gateway learns a work item's collaboration channel

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [gateway](../../../capabilities/gateway.md) | Slack resolution order (thread binding → published room → static `slack.rooms` → held); how an instance publishes rooms (`PUT /api/v1/gateway/rooms`, a replace-set at every registration, on change and every 30 s); drain, holder and prune rules; `gateway.rooms`; the store and flow diagram name rooms | issue-505 row added |
| [channels](../../../capabilities/channels.md) | The gateway note says a declared collaboration channel is published as a room, so a collaborator's top-level message reaches the work item | issue-505 row added |

The issue-496 spec's R5.2 and R5.7 carry an amendment note naming rooms
([requirements](../../issue-496/requirements.md)).

## Documentation

| Document | What changed |
|----------|--------------|
| [docs/guide/gateway.md](../../../guide/gateway.md) | "The move", step 1: collaboration channels need no `slack.rooms` entry; `slack.rooms` is only for a channel no instance declares |
| `skills/the-loop/templates/gateway-config.yaml` | the `slack.rooms` comment says the same |
| [the-loop-gateway.v1.yaml](../../../api-specs/openapi/the-loop-gateway.v1.yaml) | `PUT /api/v1/gateway/rooms` and `RoomsBody`; the description lists `/rooms` among the registrations |

`gateway-config.schema.json` is left unchanged. Its `slack.rooms` description is still
accurate: a static room covers a channel that no binding or published room covers.
