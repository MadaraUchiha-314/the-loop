---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#429"
---

# Documentation: the stop gate blocks on a node the work item never entered

> The ready-to-ship gate's documentation item: the affected capability docs are updated in
> the same pull request as the change.

## Capability docs

**[`docs/capabilities/process-graph.md`](../../../capabilities/process-graph.md)** owns the
graph runtime, `check`, and the harness gate's contract.

- A new requirement under *State, recovery and the escape hatch*: the stop gate SHALL
  NOT ask about a node the work item never entered. It covers:
  - `pointer` on every report;
  - the walk to the pointer;
  - the inconclusive rules;
  - the accepted residual;
  - the `state:` line.
- A history row for issue-429, above issue-343.

**[`docs/capabilities/cli.md`](../../../capabilities/cli.md)**: `check`'s requirement
says the report keeps the pointer under `--recompute`, and that the `state:` line names
it when it differs.

## Documentation

- [`docs/cli/commands/check.md`](../../../cli/commands/check.md): the `--recompute`
  section explains the derived position, shows the new `state:` line, and says why
  the stop gate reads both positions. The JSON paragraph lists `pointer`.
- [`skills/the-loop/reference/automation.md`](../../../../skills/the-loop/reference/automation.md):
  the Stop gate asks about the node the item is at, never one it has not entered.
- `POST /graph/check` (route docstring and
  [`docs/api-specs/openapi/the-loop.v1.yaml`](../../../api-specs/openapi/the-loop.v1.yaml))
  and the `check_work_item` MCP tool describe `pointer`.

## Not affected

- `docs/capabilities/distribution.md`: the gate is still declared the same way in
  `hooks/hooks.json`.
- `docs/capabilities/control-plane.md`: no route or parameter changed, only a
  response key.
