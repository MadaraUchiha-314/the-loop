---
type: execution-log
workItem: ""
phase: not-started           # not-started | requirements-definition | design | tasks-breakdown | implementation | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: <work item title>

> Append-only log of progress for the user's visibility. Checked in alongside the spec
> at `docs/specs/<id>/execution-log.md`. The-loop keeps the work item's phase label in
> the ticketing system in sync with the `phase` front-matter above, and self-checks
> (runs tests at logical checkpoints) recording the outcome here.

## Phase transitions
| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition |  |  |  |
| design |  |  |  |
| tasks-breakdown |  |  |  |
| implementation |  |  |  |
| needs-review |  |  |  |
| complete |  |  |  |

## Progress entries

### <timestamp> — <short summary>
- **Phase:** <current phase>
- **Did:** what was done
- **Checkpoint/tests:** commands run and their result (pass/fail + evidence)
- **Next:** what is next
- **Blockers:** anything waiting on a human (link the ticket comment)

## Review cycles
| Cycle | Type (self/critic) | Reviewer | Outcome | Link |
|-------|--------------------|----------|---------|------|
|       |                    |          |         |      |

## Final validation evidence
The evidence presented to the user proving acceptance criteria are met.
