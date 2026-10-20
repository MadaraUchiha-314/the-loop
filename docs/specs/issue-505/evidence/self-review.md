---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#505"
---

# Self-review: the gateway learns a work item's collaboration channel

Two rounds, the operator's cap (`the-loop critic policy`: `selfReviewCount: 2`,
`stopOnNoNewFindings: true`). Round 1 found three things: one doc fix, two won't-fix with
a reason. Round 2 found nothing new.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | `[claude/opus-5.5]` | new findings | R1-1 design names `_prune_instances` → fixed in its own commit; R1-2 `document()["rooms"]` shows refused rooms → won't-fix (logged, and the gateway's `/instances` is the authority); R1-3 hook publishes synchronously on the dispatch thread → won't-fix (same shape as `publish_binding`, bounded by the 10 s timeout, no deadlock) | [PR #506 comment](https://github.com/MadaraUchiha-314/the-loop/pull/506#issuecomment-6282328862) |
| 2 | `[claude/opus-5.5]` | zero (converged) | — | [PR #506 comment](https://github.com/MadaraUchiha-314/the-loop/pull/506#issuecomment-6282329076) |
