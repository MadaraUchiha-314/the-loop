---
description: Execute the task DAG for a work item from its requirements.md, design.md and tasks.md — implement, self-check, self/critic-review (implementation phase).
argument-hint: "<ticket-id | spec-dir> (e.g. 42 | issue-42)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Task
---

# the-loop: execute-tasks `$ARGUMENTS`

Implement a work item by executing its approved **tasks.md** against **requirements.md**
and **design.md** — the implementation → review portion of the loop. A slice of
`/the-loop:work-on`; `work-on` remains the superset.

**Read the `the-loop` skill, `reference/workflow.md`, `reference/context.md` and
`reference/tooling.md` first.**
Load `.the-loop/config.yaml`; apply any per-task `overrides` from the spec front-matter.

**Start clean.** Entering implementation crosses a phase boundary: apply
`contextManagement.phaseBoundary` (default `clear`) so execution runs against the
locked spec files read from disk, not the drafting conversation (plan-mode style).

## Steps

1. **Locate & load the spec.** Resolve `$ARGUMENTS` to `docs/specs/<id>/` and read
   `requirements.md`, `design.md`, `tasks.md`, and `execution-log.md`. Use the log's
   `phase` and tasks' checkmarks to **resume** rather than restart.

2. **Implementation** (`implementation`). Execute the task DAG autonomously in dependency
   order. **Tick each task in `tasks.md` (`- [ ]` → `- [x]`) as it completes.** Maintain
   `execution-log.md`: append progress and run tests (unit/integration per config) at the
   task checkpoints — self-check as you go. Use the configured tooling; same commands as
   CI. Keep the ticket phase label in sync. **After each completed task, manage the
   context window: checkpoint first (checkmark, log entry with a concrete Next, WIP
   committed/noted), then reset per `contextManagement.taskBoundary` (default
   `compact`). Mid-task, compact only — never clear. Never reset without the
   checkpoint.** See `reference/context.md`.

3. **Review** (`needs-review`). Run up to `reviews.selfReviewCount` self-reviews then
   `reviews.criticReviewCount` critic reviews (configured critics) BEFORE escalating to a
   human. Then run the **security review gate** (`security.review` — built-in
   security-review skill when available, else the-loop's checklist in
   `reference/security.md`); risk tier ≥ `security.review.humanSignOffMinTier` waits
   for a named human security sign-off. Record every review as a PR/ticket comment and
   in the log's review table (the security round in its Security review section).
   Notify via configured messaging channels when a human action is pending.

4. **Evidence + reviewer briefing (required gate).** Present validated evidence that the
   acceptance criteria are met (tests, screenshots, logs). BEFORE requesting human
   review, **post/update the R10 reviewer briefing in the PR** — produced from
   `userInteraction.prSummary.templatePath` (the-loop's internal
   `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/pr-briefing.md`): a
   condensed, prioritized summary (where to focus), **mermaid** diagram(s), and the
   low-level decisions the harness made. This is a ready-to-ship gate item
   (`userInteraction.prSummary.required`) — educating the reviewer is mandatory, not
   optional; do not request review without it.

5. **Next step:** once every task is checked and reviewed, `/the-loop:finish-tasks <id>`.

Capture learnings (`learnings/`) and durable decisions (`docs/decisions/`) as you go.
