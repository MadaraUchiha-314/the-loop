---
description: Run "the-loop" on a work item (GitHub issue or Jira id) via the 3-phase spec workflow — requirements → design → tasks → execute, with self/critic review.
argument-hint: "<ticket-id> (e.g. 12 | issue-12 | PROJ-42)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Task
---

# the-loop: work-on `$ARGUMENTS`

Drive a single work item end-to-end with minimal/no human intervention, following the
Kiro-style 3-phase spec workflow (https://kiro.dev/docs/specs/). Load
`.the-loop/config.yaml` first; apply any per-task `overrides` from the work item's
front-matter. Specs live in `<workflow.specDir>/<id>/` (default `docs/specs/<id>/`).

## Phase state machine

Keep the work item's phase **label** in the ticketing system in sync at every
transition (label = `<workflow.phaseLabelPrefix><phase>`, e.g. `loop:design`), and
mirror it in the execution log's `phase` front-matter:

`not-started → requirements-definition → design → tasks-breakdown → implementation → needs-review → complete`

## The loop

1. **Resume or start.** Look in `docs/specs/<id>/` for existing
   `requirements.md`/`bugfix.md`, `design.md`, `tasks.md`, `execution-log.md`. Use the
   execution log's `phase` and the specs' `status` to resume from where you left off
   rather than restarting.

2. **Identify collaborators up-front** from the work item + `collaborators.yaml`. Not
   every task needs every persona (a bug fix needs the engineer; a content fix may not).

3. **Phase 1 — Requirements** (`requirements-definition`). Create
   `docs/specs/<id>/requirements.md` (or `bugfix.md` for a bug) from the template:
   introduction, user stories, and EARS acceptance criteria. Post/link it on the ticket
   and **request human review**. Do not proceed until approved (record approver →
   paper trail). `requireHumanReviewPerPhase` defaults to true.

4. **Phase 2 — Design** (`design`). Create `docs/specs/<id>/design.md` derived from the
   approved requirements: architecture, components/interfaces, data models, error
   handling, testing strategy. Request human review; do not proceed until approved.

5. **Phase 3 — Tasks** (`tasks-breakdown`). Create `docs/specs/<id>/tasks.md`: a DAG of
   small, verifiable tasks, each referencing the requirement(s) it satisfies and its
   dependencies. Request human review; do not proceed until approved.

6. **Implementation** (`implementation`). Execute the task DAG autonomously. Maintain
   `docs/specs/<id>/execution-log.md`: append progress, check off tasks, and run tests
   (unit/integration per config) at logical checkpoints — self-checking as you go.
   Same tooling as CI; logging/observability identical to runtime.

7. **Review** (`needs-review`). Run up to `reviews.selfReviewCount` self-reviews and
   `reviews.criticReviewCount` critic reviews (configured critics, e.g. a different
   harness/model) BEFORE escalating to the human reviewer. Record every review as a
   PR/ticket comment and in the execution log's review table. Notify via configured
   messaging channels when a human action is pending.

8. **Complete** (`complete`). Present validated evidence that the acceptance criteria
   are met (tests, screenshots, logs) on the PR; record it in the execution log.

9. **Capture learnings.** Add to `learnings/learnings.md` (+ a `learning-<nnn>.md`) for
   any user/system feedback worth remembering. Log durable decisions under
   `docs/decisions/`.

All questions and decisions go through ticket/PR comments (paper trail). The checked-in
specs + execution log are the single record of the work.
