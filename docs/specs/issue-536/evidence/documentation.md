---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#536"
---

# Documentation: publish a work item's spec chain as one Claude doc

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `docs/capabilities/spec-workflow.md` | The `claude-doc` requirement (default, conflict, read-before-rewrite, handoff exception); the explainer page can be a tab of the spec-chain doc | issue-536 |
| `docs/capabilities/process-graph.md` | The `claude-doc` row's resolution, the swap after a handoff, and the `claudeDoc` freeze (written only when true) | issue-536 |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/cli/commands/graph.md` | The checklist example and a `claude-doc` paragraph |
| `docs/cli/state.md` | The `claudeDoc` row; the "written only when set" sentence |
| `skills/the-loop/SKILL.md` | The doc bullet |
| `skills/the-loop/reference/workflow.md` | New section: The spec chain as one Claude doc |
| `skills/the-loop/reference/explainer.md` | Publishing table: the doc row and the fall-through fix |
| `skills/the-loop/reference/collaboration.md` | The doc as a surface |
| `commands/explain.md` | The doc tab case |
