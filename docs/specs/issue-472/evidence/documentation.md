---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#472"
---

# Documentation: make the phase-selection comment easier to read (issue-472)

## Capability docs

- **[`docs/capabilities/process-graph.md`](../../../capabilities/process-graph.md)**
  gains the EARS criterion for the layout: the quick start, two groups, a heading and
  emoji per question, the default before the rows, explanations collapsed, rows
  unchanged, and `<details>` unfolded in Slack. Plus a history row.

## Documentation

- **CLI reference:** `docs/cli/commands/graph.md` § *The first phase* gains a paragraph
  on how the comment is laid out. Its example rows are unchanged, because the rows are.
- **Not changed, and why:** the skill (`skills/the-loop/`) describes what the gate asks,
  not how the comment looks, so nothing there became wrong. No config key, state key or
  reply grammar changed, so `docs/cli/state.md` and the config references are unaffected.
