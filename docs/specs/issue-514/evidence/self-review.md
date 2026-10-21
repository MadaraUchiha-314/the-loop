---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#514"
---

# Self-review: split `/the-loop:init` into `/init`, `/init-cli` and `/init-gateway`

> The `self-review` node's proof. One row per round, per `reference/reviewing.md`:
> attribution prefix, own-comment marker, reply-first-then-fix, stop on zero new
> findings, escalate on a repeated finding. Outcome is one of: new findings ·
> zero (converged) · escalated · **unavailable** (the configured reviewer could not
> run — it does NOT count toward `reviews.selfReviewCount`, read with
> `the-loop critic policy`).

Policy (`the-loop critic policy`): `selfReviewCount: 2`, `stopOnNoNewFindings: true`,
`escalateOnRepeatFinding: true`.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | claude/opus-5.5 | new findings (3) | 1. stale `/the-loop:init` pointers for the CLI config (rung summary in both schema copies, two code comments) → will-fix, `58d59bef` · 2. precedence step 1 named only the harness config → will-fix, `ed58885d` · 3. `/init` named a manifest "gateway entry" that does not exist → will-fix, `5d34c425` | https://github.com/MadaraUchiha-314/the-loop/pull/515#issuecomment-6309446971 |
| 2 | claude/opus-5.5 | zero (converged) | none | https://github.com/MadaraUchiha-314/the-loop/pull/515#issuecomment-6309455796 |
