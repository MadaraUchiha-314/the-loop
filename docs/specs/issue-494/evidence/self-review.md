---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#494"
---

# Self-review: gate the brainstorm on its author's approval

> The `self-review` node's proof, one row per round, per `reference/reviewing.md`. The
> operator's policy (`the-loop critic policy`) is `selfReviewCount: 2`,
> `stopOnNoNewFindings: true`, `escalateOnRepeatFinding: true`.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | `[claude/opus-5.5]`, the implementing session, over `origin/main...HEAD` and the spec | 1 new finding | **S1** (medium): with `whenPresent` skipping, a gate whose `brainstorm.md` was deleted while open passed with no matching edge and escalated on `no_edge` → fixed `d31c1a1`, pinned by `test_a_brainstorm_removed_while_the_gate_is_open_does_not_wedge_it` (red before, green after). The same pass also corrected the red-before evidence to run against `origin/main` rather than a stale local `main` | [PR #495](https://github.com/MadaraUchiha-314/the-loop/pull/495) |
| 2 | `[claude/opus-5.5]`, a fresh-context reviewer given round 1's finding | in progress | — | — |
