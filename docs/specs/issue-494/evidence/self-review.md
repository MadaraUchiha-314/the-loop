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
| 2 | `[claude/opus-5.5]`, a fresh-context reviewer given round 1's finding, over `origin/main...b1d774a` | 3 new findings (cap reached) | **S2** (medium): round 1's `pass` edge let an agent delete `brainstorm.md` at the gate and walk into requirements with no human; deleting it after changes-requested routed on `not-entered` past the gate → fixed `40a63cc`: `HookContext.visited`, a missing brainstorm blocks once the gate was entered, the `pass` edge removed; pinned by `test_deleting_the_brainstorm_at_its_gate_does_not_open_it` and `test_deleting_the_brainstorm_after_changes_requested_does_not_skip_them` (both red before the fix). **S3** (low): `--recompute` reports a brainstormed item at `brainstorm-approval`, as every approval gate reads `wait` without an event → documented in `process-graph.md` (pre-existing behaviour of all gates, not changed here). **S4** (low): `workflow.md` listed only two approval nodes → fixed `40a63cc` | [PR #495](https://github.com/MadaraUchiha-314/the-loop/pull/495) |

**S2 is a regression round 1's own fix introduced**, not S1 raised again: S1's remedy
(route on `pass`) is what opened the bypass. Both are now pinned by tests that need the
fail-closed behaviour.

**The rounds stopped at the cap, not at zero findings.** The critic round ran on
`b1d774a`, before S2's fix; see the note in `critic-review.md`. After the last fix: 6128
passed and 21 failed, the same 21 as on the base commit (they read this host's live
poller). Lint, format, pyright and `validate` are clean.
