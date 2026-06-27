---
description: Run "the-loop" on a work item (GitHub issue or Jira id) — plan, execute, self/critic review, escalate.
argument-hint: "<ticket-id> (e.g. 12 | issue-12 | PROJ-42)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Task
---

# the-loop: work-on `$ARGUMENTS`

Drive a single work item end-to-end with minimal/no human intervention, following
the loop. Load `.the-loop/config.yaml` first; apply any per-task `overrides` from the
work item's front-matter.

## The loop

1. **Resume or start.** Check for an existing
   `docs/delivery-plans/<id>-delivery-plan.md` and
   `docs/execution-logs/<id>-execution-log.md`. If present, resume from where the
   execution log left off instead of restarting.

2. **Define the work item.** Ensure the ticket has a clear description, detailed goal
   and acceptance criteria. If missing, draft them and confirm via a ticket comment.

3. **Identify collaborators up-front** from the work item + `collaborators.yaml`.
   Not every task needs every persona (a bug fix needs the engineer; a content fix
   may not need the engineer).

4. **Plan.** Create `docs/delivery-plans/<id>-delivery-plan.md` from the template.
   Post it / link it on the ticket and request approval from the required
   collaborators. **Do not start execution until the plan is approved.** All
   questions and decisions go through ticket comments (paper trail).

5. **Execute.** Once approved, deliver the work autonomously. Maintain
   `docs/execution-logs/<id>-execution-log.md`: append progress, and run tests
   (unit/integration per config) at logical checkpoints — self-checking as you go.
   Logging/observability must match runtime; same tooling as CI for all checks.

6. **Self-review + critic-review.** Run up to `reviews.selfReviewCount` self-reviews
   and `reviews.criticReviewCount` critic reviews (using configured critics, e.g. a
   different harness/model) BEFORE escalating to the human reviewer. Record every
   review as a PR/ticket comment and in the execution log's review table.

7. **Escalate to human** only when reviews are exhausted or a decision is required.
   Notify via configured messaging channels if a human action is pending.

8. **Present validated evidence** that the acceptance criteria are met (tests,
   screenshots, logs) on the PR, and record it in the execution log.

9. **Capture learnings.** Add to `learnings/learnings.md` (+ a `learning-<nnn>.md`)
   for any user/system feedback worth remembering. Log significant decisions under
   `docs/decisions/`.

Stay within the loop; keep the ticket and checked-in plan/log as the single record.
