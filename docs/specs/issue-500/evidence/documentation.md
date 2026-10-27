---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#500"
---

# Documentation: record-feedback appends duplicate sibling headings when a gate is approved twice on one day

> The `capability-docs` node's proof (issue-174): both sections, same PR as the change.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`docs/capabilities/process-graph.md`](../../../capabilities/process-graph.md) | The `record-feedback` bullet now states that each block opens with a `### <date> — <outcome>` heading and that a repeat is suffixed `(n)`, with the smallest free `n ≥ 2`, never renumbering one already written | issue-500 row, newest |

## Documentation

No user-facing document changes. The README, the docs site and the operating-model skill
do not describe the review-block heading format, and the templates' `## Review comments`
blurb ("Append-only and attributed") stays true.
