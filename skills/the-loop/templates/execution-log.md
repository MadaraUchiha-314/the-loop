---
type: execution-log
workItem: ""
phase: not-started           # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
# repos:                     # OPTIONAL (issue-183). The CONTRIBUTING repositories this
#   - <owner>/<repo>         #   work item raises pull requests in — one inner loop each,
#   - <owner>/<other>        #   state under pr-loops/<owner>__<repo>/pr-<n>/ here in the
                             #   ORIGIN repository (the one the ticket was created in).
                             #   `await-inner-loops` then holds `implementation` until each
                             #   declared repository has a loop AND every started loop has
                             #   finished. Omit for single-repository work: the gate then
                             #   behaves exactly as it did before the key existed.
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
> PR, a stacked series, a follow-up after review, or **one PR per contributing
> repository** — the multi-repo shape, where the outer loop stays in the repository the
> ticket was created in and each other repository gets its own PR and inner loop) — list
> every one of them here, not just the latest. Name the repository in the PR column when
> it is not this one. Each PR carries the auto-execute
> label **and is recorded against this work item as it is opened**
> (`the-loop sessions link-pr`, `reference/automation.md`) so its activity routes back
> to this work item's session, and the work item
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

## Verification results

> **Only when this work item declared `test-planning` away** (issue-179). With a
> `testing-plan.md` the `verification` node records its results *there*, against the
> matrix rows it planned, and this section stays as the template left it. Without one,
> this is where the proof lives — and `verification` blocks until it is filled in, because
> skipping the plan removes the document, never the verifying.

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
|                   |         | pass \| fail | link or `evidence/<file>` |

## Design critic review

> **Only when this work item selected the opt-in `design-critic-review` phase** (issue-188)
> — a different model/harness reading the **locked `design.md`** against the requirements,
> before the testing plan and the task DAG are derived from it. The node blocks until this
> section is filled in; a work item that did not select the phase leaves it as the template
> left it. Rounds follow `reference/reviewing.md` unchanged: attribution prefix, own-comment
> marker, reply-first-then-fix, stop on zero new findings, escalate on a repeated finding.
> A round that could not run is recorded as **`unavailable`** with the cause and does NOT
> count toward `reviews.criticReviewCount`.

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
|       |                             | new findings \| zero (converged) \| escalated \| unavailable | | |

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

## Documentation

> Which **user-facing** documents this work item changed — `README.md`, the documentation
> site under `docs/`, and the operating-model skill with its `reference/` docs. Capability
> docs above are the organized view of specs, written for a reader who already uses the
> project; this section is the surface a reader meets *before* that, and it rots the same
> way, so it is updated **in the same PR** as the change (`reference/workflow.md`,
> ready-to-ship gate). The `capability-docs` node gates this section alongside the one
> above (issue-174).
>
> A work item that genuinely changed no user-facing documentation says so here **with the
> reason** — "internal refactor, no described behaviour changed" is an answer; a blank is
> not. The section is never deleted to shorten the log. A row names a **document**, never a
> token, a credential or an internal hostname: this tree is as public as the repository.

| Document | What changed |
|----------|--------------|
|          |              |
