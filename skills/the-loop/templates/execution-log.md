---
type: execution-log
workItem: ""
phase: not-started           # not-started | brainstorming | requirements-definition | design | tasks-breakdown | implementation | needs-review | complete
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
| tasks-breakdown |  |  |  |
| implementation |  |  |  |
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

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
|       |                             |          |         |      |

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** <security-review skill | the-loop checklist> (`security.review.mechanism`)
- **Outcome:** <pass | findings fixed (link threads) | escalated>
- **Human sign-off:** <n/a (tier below `security.review.humanSignOffMinTier`) | @handle + link>

## Final validation evidence

The evidence presented to the user proving acceptance criteria are met.
