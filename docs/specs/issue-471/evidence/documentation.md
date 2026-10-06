---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#471"
---

# Documentation: the spec chain as one Claude artifact (issue-471)

## Capability docs

- **[`docs/capabilities/process-graph.md`](../../../capabilities/process-graph.md)**
  gains the EARS criterion for the `claude-artifact` row: offered where the surface row
  is, frozen only when resolved to `claude` (or an unknown harness), read back only as
  `true`, one fixed prompt line, and never a route, skip or gate answer. Plus a history
  row.
- **[`docs/capabilities/spec-workflow.md`](../../../capabilities/spec-workflow.md)**
  gains the criterion for what the session does with it (one artifact, a tab per file,
  republish, link once, files stay the source of truth). Plus a history row.

## Documentation

- **Skill:** `skills/the-loop/SKILL.md` gains one operating-principles bullet.
  `reference/workflow.md` gains § *The spec chain as one Claude artifact (issue-471)*
  with the seven-step procedure. `reference/collaboration.md` notes that the artifact is
  a reading surface, never a third place to decide.
- **CLI reference:** `docs/cli/commands/graph.md` shows the row in the checklist
  example and explains it. `docs/cli/state.md` documents `claudeArtifact` in the state
  table and the archive's `selections`.
- **Not changed, and why:** `README.md` and the documentation site's front pages do not
  describe the checklist's rows, so nothing there became wrong. No config key was added,
  so the configuration reference is unchanged.
