---
type: tasks
phase: tasks-breakdown
workItem: "issue-150"
status: approved
approvedBy: [MadaraUchiha-314]
overrides: {}
---

# Tasks: Replace the README workflow mermaid diagram with an Excalidraw diagram

> Phase 3 of 3, derived from [requirements.md](requirements.md) and
> [design.md](design.md).

## Task list

- [x] T1 — Author the workflow scene (generator script → `.excalidraw` JSON),
  content-matched to the mermaid original (req 2).
- [x] T2 — Export `docs/assets/the-loop-workflow.svg` via Excalidraw's `exportToSvg`
  with fonts embedded and `exportEmbedScene` on (req 3); verify no scripting in the
  output.
- [x] T3 — Replace the README mermaid block with the SVG embed plus a pointer to the
  editable sources (req 1).
- [x] T4 — Verify: markdownlint on changed markdown, scene JSON validity, visual
  check of the rendered SVG against the mermaid original.
