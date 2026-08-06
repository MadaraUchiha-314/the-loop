---
type: execution-log
workItem: ""
phase: not-started           # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: <work item title>

> Append-only log of progress for the user's visibility. Checked in alongside the spec
> at `docs/specs/<id>/execution-log.md`. The-loop keeps the work item's phase label in
> the ticketing system in sync with the `phase` front-matter above, and self-checks
> (runs tests at logical checkpoints) recording the outcome here. The log doubles as
> the **resume anchor for context resets** (`reference/context.md`): every reset (clear
> or compact) is preceded by a checkpoint entry here, and a fresh window re-enters by
> reading the latest entry's **Next:** first.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition |  |  |  |
| design |  |  |  |
| test-planning |  |  |  |
| tasks-breakdown |  |  |  |
| implementation |  |  |  |
| verification |  |  |  |
| needs-review |  |  |  |
| complete |  |  |  |

## Pull requests

> A work item may be delivered by **several** PRs (a spec PR then an implementation
> PR, a stacked series, a follow-up after review, or one PR per repository) — list
> every one of them here, not just the latest. Each PR carries the auto-execute
> label so its activity routes back to this work item's session, and the work item
> is complete only once **all** of them are merged or closed (`finish-tasks`).

| PR | Scope / tasks | Status |
|----|---------------|--------|
|    |               | open \| merged \| closed |

## Progress entries

### <timestamp> — <short summary>

- **Phase:** <current phase>
- **Did:** what was done
- **Checkpoint/tests:** commands run and their result (pass/fail + evidence)
- **Next:** what is next
- **Context:** *(only when this checkpoint precedes a reset)* cleared | compacted, and why
- **Blockers:** anything waiting on a human (link the ticket comment)

## Review cycles

> Outcome is one of: new findings · zero (converged) · escalated · **unavailable** (the
> configured critic could not run — it does NOT count toward `reviews.criticReviewCount`).

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
|       |                             |          |         |      |

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** <security-review skill | the-loop checklist> (`security.review.mechanism`)
- **Outcome:** <pass | findings fixed (link threads) | escalated>
- **Human sign-off:** <n/a (tier below `security.review.humanSignOffMinTier`) | @handle + link>

## Final validation evidence

The evidence presented to the user proving acceptance criteria are met. **Summarised
from `testing-plan.md`'s Verification results** (the `verification` node produced the
raw record — command, outcome, committed evidence per activity); this section maps it
onto the acceptance criteria rather than re-deriving it. Committed evidence files live
under `<specDir>/<id>/evidence/`.

## Capability docs

> Which living capability docs this work item changed, and the history row that traces
> each behaviour back to it. Capability docs are the **organized view of specs** — the
> single source of truth for a capability's *current* behaviour — so they are updated
> **in the same PR** as the change (`workflow.capabilitiesDir`), and this section is what
> the `capability-docs` node gates on. A work item that genuinely changed no capability
> says so here, and why; the section is never deleted to shorten the log.

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
|                |              |             |
