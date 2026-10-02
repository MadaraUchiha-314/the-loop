# Documentation (issue-453)

## Capability docs

| Doc | What changed |
|-----|--------------|
| `docs/capabilities/cli.md` | the lifecycle-authority requirement now says what registered means (session **or** this instance's control record for an item not ended), that the record source reaches the work item only, that `ticket close` cancels a parked start idempotently, and what grants nothing; a history row |

## Documentation

| Doc | What changed |
|-----|--------------|
| `docs/cli/commands/ticket.md` | `ticket close`: the two ways a work item is registered, what is refused, the start cancellation, `startCancelled`, idempotency, the session-backed path unchanged |
| `docs/decisions/decision-141.md`, `docs/decisions/decisions.md` | the decision refining decision-140 D8, and its index row |
| `cli/the_loop/api/mcp.py` | the `close_ticket` tool's docstring, which is the MCP tool's description |

`skills/the-loop/SKILL.md`, `reference/automation.md` and the OpenAPI document were not
changed: the skill names the verb without describing the ownership rule, and the route's
body and response schema are as they were (the new field rides the open response
object).
