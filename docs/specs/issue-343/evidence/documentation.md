---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#343"
---

# Documentation: an operator can bring their own graphs and bind commands to them

> The organized view must not rot: every capability and user-facing page this change makes
> wrong is updated in the same pull request.

## Capability docs

| Page | What changed |
|---|---|
| [`docs/capabilities/process-graph.md`](../../../capabilities/process-graph.md) | A new *Graphs of the operator's own (issue-343)* section in EARS form (declaration, naming, compiler rules, `command:` grammar, command bindings, fail-closed selection, `guest`, scoped attachments, `graph loops`); the "graph is internal" bullet and the repository-hooks section's closing bullet reworded (repositories still cannot author a graph; operators now can); the intro names the operator's graphs; a history row |

## Documentation

| Page | What changed |
|---|---|
| [`docs/cli/graphs.md`](../../../cli/graphs.md) (new) | *Bringing your own graph*: writing one, the rules it is held to, declaring it, what a command word may be, checking it with `graph loops`, how a work item picks it, what to review before adopting one |
| [`docs/.vitepress/config.mts`](../../../.vitepress/config.mts) | The new page in the *Extending* sidebar, beside *Adding a hook* |
| [`docs/cli/hooks.md`](../../../cli/hooks.md) | No longer says nobody declares loops; documents `attach[].loops`; links the new page |
| [`docs/cli/commands/graph.md`](../../../cli/commands/graph.md) | A `loops` section: output, JSON shape, exit codes |
| [`docs/config/cli/routing-options.md`](../../../config/cli/routing-options.md) | `graph.hooks.attach[].loops`, `graph.graphs` and each of its four keys (the docs-parity test requires a heading per schema leaf) |
| [`docs/decisions/decision-136.md`](../../../decisions/decision-136.md) (new) + [`decisions.md`](../../../decisions/decisions.md) | The decision record and its index row |
| [`skills/the-loop/SKILL.md`](../../../../skills/the-loop/SKILL.md) | The graph paragraph says an operator may declare graphs and that an armed session follows the graph's nodes; the CLI-config table gains a *graphs of the operator's own* row |
| [`skills/the-loop/reference/workflow.md`](../../../../skills/the-loop/reference/workflow.md) | *A graph of the operator's own*: how to work inside one (follow its nodes, run a namespaced command or say it is missing, the non-gate rules still hold, never edit the graph) |
| `.the-loop/cli-config.schema.json` + `cli/the_loop/schemas/cli-config.schema.json` | `routing.graph.graphs` and `attach[].loops`, described (identical copies, pinned by the parity test) |
| `.the-loop/cli-config.yaml`, `skills/the-loop/templates/cli-config.yaml` | Commented samples of both keys |
| `cli/the_loop/eventlog.py` (`EVENT_TYPES`) | `control.command` documents its `loop` field |

**Not affected**, checked rather than assumed:

- `docs/api-specs/openapi` — no route changes; `graph loops` is local, like `graph hooks`.
- `README.md` — describes the loop at a level the change does not contradict.
- `commands/*.md` (the slash commands) — each names its own shipped loop; a custom graph
  steers the session through its nodes' `command:`, which the workflow reference covers.
- `docs/config/harness-config.md` — the harness config gains nothing; the declaration is
  the operator's CLI config (decision-123).
