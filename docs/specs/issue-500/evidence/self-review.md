---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#500"
---

# Self-review: record-feedback appends duplicate sibling headings when a gate is approved twice on one day

> The `self-review` node's proof. Policy (`the-loop critic policy`): two self rounds,
> stop on zero new findings, escalate on a repeated finding. Both rounds were posted on
> PR #526.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | claude/opus-5.5 | new findings (1) | 1 the scenario checked R1.2's unchanged first heading with `endswith` only → will-fix → full-match regex (acce996b). Checked with no change: append-only, CRLF, `###` in a fence, no untrusted input in the heading | [round 1](https://github.com/MadaraUchiha-314/the-loop/pull/526#issuecomment-6431640052) |
| 2 | claude/opus-5.5 | zero (converged) | none | [round 2](https://github.com/MadaraUchiha-314/the-loop/pull/526#issuecomment-6431641626) |
