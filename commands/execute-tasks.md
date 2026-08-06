---
description: Execute the task DAG for a work item — implement, verify against the testing plan, self-check, self/critic-review (implementation → verification → review).
argument-hint: "<ticket-id | spec-dir> (e.g. 42 | issue-42)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Task
---

# the-loop: execute-tasks `$ARGUMENTS`

Implement a work item by executing its approved **tasks.md** against **requirements.md**,
**design.md** and **testing-plan.md** — the implementation → verification → review
portion of the loop. A slice of `/the-loop:work-on`; `work-on` remains the superset.

**Read the `the-loop` skill, `reference/workflow.md`, `reference/context.md` and
`reference/tooling.md` first.**
Load `.the-loop/harness-config.yaml`; read every custom instruction doc it registers
(`customInstructions.docs`, in order — the operator's conventions and styles,
`reference/instructions.md`, and `the-loop instructions` to confirm each one resolved);
apply any per-task `overrides` from the spec front-matter.

**Start clean.** Entering implementation crosses a phase boundary: apply
`contextManagement.phaseBoundary` (default `clear`) so execution runs against the
locked spec files read from disk, not the drafting conversation (plan-mode style).

## Steps

1. **Locate & load the spec.** Resolve `$ARGUMENTS` to `docs/specs/<id>/` and read
   `requirements.md`, `design.md`, `testing-plan.md`, `tasks.md`, and
   `execution-log.md`. Use the log's
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

   **Stay monitorable.** Register the session for webhook/poll routing
   (`the-loop sessions register`, see the skill's `reference/automation.md`). When the
   ticketing provider is **not GitHub** (Jira, …), the PR is the monitorable GitHub
   object: once the PR exists, **add the `routing.autoExecuteLabel` (from the operator's
   CLI config, decision-032; default `the-loop: auto-execute`) to the PR directly** and
   register against the PR's own ref (`github:OWNER/REPO#<pr-number>`), so PR activity
   still resumes this session. **If the item takes more than one PR**, label **every**
   one of them and list them all in the execution log's **Pull requests** table — one
   PR merging does not end the work item.

3. **Verification** (`verification`). Once every task is ticked, execute
   `testing-plan.md`: bring up the declared environment, run each planned activity, and
   tick it **only** once it has run and its evidence is recorded. Write the per-activity
   command, outcome and evidence link into the plan's **Verification results**, and commit
   the evidence itself under `docs/specs/<id>/evidence/` — redacted (tokens, cookies,
   personal data, internal hostnames), because that directory is as public as the
   repository. UI verification captures screenshots of each verified state and an
   animated capture (GIF) when the behaviour is a *flow*. An activity that cannot run
   stays unticked: record why, then replan the matrix (with the reason) or escalate; if
   the environment will not come up, escalate rather than passing the gate. See
   `reference/testing.md`. (Runnable on its own as `/the-loop:verify-work <id>`.)

4. **Review** (`needs-review`). Run up to `reviews.selfReviewCount` self-reviews then
   `reviews.criticReviewCount` critic reviews (configured critics) BEFORE escalating to a
   human. Then run the **security review gate** (`security.review` — built-in
   security-review skill when available, else the-loop's checklist in
   `reference/security.md`); risk tier ≥ `security.review.humanSignOffMinTier` waits
   for a named human security sign-off. Record every review as a PR/ticket comment and
   in the log's review table (the security round in its Security review section).
   Notify per the `notifications.events` filters (harness-config.yaml), resolving
   recipients by role from `.the-loop/collaborators.yaml`, when a human action is
   pending.

5. **Evidence + reviewer briefing (required gate).** Present validated evidence that the
   acceptance criteria are met — **summarised from the verification results** rather than
   re-derived (tests, screenshots, logs). BEFORE requesting human
   review, **post/update the R10 reviewer briefing in the PR** — produced from
   `userInteraction.prSummary.templatePath` (the-loop's internal
   `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/pr-briefing.md`): a
   condensed, prioritized summary (where to focus), **mermaid** diagram(s), and the
   low-level decisions the harness made. This is a ready-to-ship gate item
   (`userInteraction.prSummary.required`) — educating the reviewer is mandatory, not
   optional; do not request review without it.

6. **Next step:** once every task is checked and reviewed, `/the-loop:finish-tasks <id>`.

Capture learnings (`learnings/`) and durable decisions (`docs/decisions/`) as you go.
