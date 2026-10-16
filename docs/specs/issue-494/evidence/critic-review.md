---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#494"
---

# Critic review: gate the brainstorm on its author's approval

> The `critic-review` node's proof. Policy (`the-loop critic policy`):
> `criticReviewCount: 1`, critic `codex` (`gpt-6.1-sol`), run with `the-loop critic run
> codex` over `origin/main...HEAD` and the spec, after self-review round 1's fix.

## Review cycles

| Round | Critic | Outcome | Findings → disposition | Link |
|-------|--------|---------|------------------------|------|
| 1 | `[codex/gpt-6.1-sol]` | 1 new finding | **C1** (P2): with `brainstorming` declared skipped but a stray `brainstorm.md` on disk, `check --recompute` scored `brainstorm-approval` as `wait`, a gate the walk never enters → fixed `b1d774a`: `classify-feedback`'s `whenPresent` also treats an artifact whose authoring node was declared skipped as absent. Pinned by `test_a_skipped_brainstorm_left_on_disk_is_not_reported_at_its_gate` (red before, green after) | [PR #495](https://github.com/MadaraUchiha-314/the-loop/pull/495) |

The critic's other checks (unauthorized commenters, repository `x-` hooks declaring the
`not-entered` outcome, the checklist, the docs) produced no findings. The one-round cap is
reached.

**Ordering note.** This round reviewed `b1d774a`. Self-review round 2 ran in parallel
and reported S2 afterwards, fixed in `40a63cc`. The fix narrows behaviour (absence now
blocks once the gate is entered) and adds no new route, so it was not sent back to the
critic: `criticReviewCount: 1` is spent. The security review (`evidence/security-review.md`) covers it.
