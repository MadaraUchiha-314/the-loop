---
description: Run "the-loop" on a work item (GitHub issue or Jira id) via the 3-phase spec workflow — requirements → design → tasks → execute, with self/critic review.
argument-hint: "<ticket-id> (e.g. 12 | issue-12 | PROJ-42)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Task
---

# the-loop: work-on `$ARGUMENTS`

Drive a single work item end-to-end with minimal/no human intervention, following the
Kiro-style 3-phase spec workflow (https://kiro.dev/docs/specs/). Load
`.the-loop/harness-config.yaml` first, then **read every custom instruction doc it registers**
(`customInstructions.docs`, in order; missing docs per `customInstructions.onMissing`)
and honor them throughout — they carry the operator's conventions and styles
(`reference/instructions.md`). Apply any per-task `overrides` from the work item's
front-matter. Specs live in `<workflow.specDir>/<id>/` (default `docs/specs/<id>/`).

**`work-on` is the superset.** The same flow is also exposed as granular commands you can
run one step at a time: `/the-loop:brainstorm` (optional) → `/the-loop:new-requirement` →
`/the-loop:create-ticket` → `/the-loop:create-design` → `/the-loop:create-tasks-plan` →
`/the-loop:execute-tasks` → `/the-loop:finish-tasks`, with `/the-loop:work-status <id>` to
report progress. `work-on` runs them end-to-end; reach for the granular commands to start
pre-ticket (or with a brainstorm) or to drive a single phase.

**Before acting, read the `the-loop` skill and its reference files** for the full rules:
`reference/workflow.md` (phases, reviews, DAG), `reference/context.md` (checkpoint-then-
reset window management), `reference/tooling.md` (which commands to run),
`reference/collaboration.md` (who to involve, paper trail),
`reference/observability.md`. The summary below is the procedure; the references are the
detail — do not lose it.

## Phase state machine

Keep the work item's phase **label** in the ticketing system in sync at every
transition (label = `<workflow.phaseLabelPrefix><phase>`, e.g. `loop:design`), and
mirror it in the execution log's `phase` front-matter (`brainstorming` is optional — enter
it only when the work needs a scratchpad; otherwise start at `requirements-definition`):

`not-started → brainstorming → requirements-definition → design → tasks-breakdown → implementation → needs-review → complete`

**Iterate, then advance.** Every artifact — starting from the optional `brainstorm.md`
root — is refined with human feedback until it is **locked** (`status: approved`); only
then does the loop move to the next phase. This is the same rule at every phase, not just
requirements.

## The loop

1. **Resume or start.** Look in `docs/specs/<id>/` for existing `brainstorm.md`,
   `requirements.md`/`bugfix.md`, `design.md`, `tasks.md`, `execution-log.md`. Use the
   execution log's `phase` and the specs' `status` to resume from where you left off
   rather than restarting.

2. **Identify collaborators up-front** from the work item + `collaborators.yaml`. Not
   every task needs every persona (a bug fix needs the engineer; a content fix may not).

   **Stay monitorable (auto-execute label + session registration).** So the-loop's CLI
   (webhook receiver / poller) can route the item's later activity back to this session:
   - **GitHub ticketing:** add the auto-execute label to the issue (create it if missing)
     and register the session (`the-loop sessions register --work-item
     github:OWNER/REPO#N …`, see the skill's `reference/automation.md`). The label's
     value is `webhooks.ghWebhook.routing.autoExecuteLabel` in the operator's **CLI
     config** (`cli-config.yaml` — resolved via `--config`/env/cwd/home, independent of
     this repo's plugin config, decision-032); read it there when reachable, otherwise
     use the documented default `the-loop: auto-execute`.
   - **Jira / other ticketing providers:** the ticket itself is not a GitHub object, but
     the **PR still is** — as soon as the PR exists, **automatically add the same
     auto-execute label to the PR directly** and register the session against the PR's
     own ref (`github:OWNER/REPO#<pr-number>`). PR comments, reviews and CI results then
     resume this session exactly as for a GitHub-ticketed item, and PR merge/close
     auto-closes it.

3. **Phase 0 — Brainstorm (optional)** (`brainstorming`). When the work starts as a fuzzy
   idea, create `docs/specs/<id>/brainstorm.md` (the **root artifact**) from the template:
   problem, options, open questions, working hypothesis. Iterate it with feedback until
   locked, then **derive** `requirements.md` from it. Skip this phase when the work is
   already well-defined.

4. **Phase 1 — Requirements** (`requirements-definition`). Create
   `docs/specs/<id>/requirements.md` (or `bugfix.md` for a bug) from the template:
   introduction, user stories, and EARS acceptance criteria — **including the Security
   considerations section** (threat-model-lite: untrusted actors, trust boundaries,
   abuse cases, fail-closed; `security.threatModel.required` — "no new attack surface"
   is written and justified, see `reference/security.md`). Post/link it on the ticket
   and **request human review**. Do not proceed until approved (record approver →
   paper trail). `requireHumanReviewPerPhase` defaults to true.

5. **Phase 2 — Design** (`design`). Create `docs/specs/<id>/design.md` derived from the
   approved requirements: architecture, components/interfaces, data models, error
   handling, testing strategy — **including the Security design section** stating how
   each requirements-phase trust boundary is enforced (`security.design.required`; a
   boundary left unenforced fails the gate). **If the work item has a user-facing
   surface**, also
   produce **UI/UX design artifacts** under `docs/specs/<id>/design/` (self-contained
   HTML+CSS+JS prototypes and/or a linked Figma file), inventory them in `design.md`, and
   iterate them with the **designer** until locked (`reference/design-artifacts.md`).
   Request human review; do not proceed until approved.

6. **Phase 3 — Tasks** (`tasks-breakdown`). Create `docs/specs/<id>/tasks.md`: a DAG of
   small, verifiable tasks, each referencing the requirement(s) it satisfies and its
   dependencies. Request human review; do not proceed until approved.

   **After each phase doc is established, update the ticket with a reference (link) to
   the checked-in artifact** — single source of truth, not a copy. Later changes to a
   spec doc are made as **edits to that file, not new comments**.

7. **Implementation** (`implementation`). Entering implementation crosses the big phase
   boundary: **reset context per `contextManagement.phaseBoundary` (default `clear`)**
   and execute against the locked spec files read from disk, not the drafting
   conversation (plan-mode style; `reference/context.md`). Execute the task DAG
   autonomously. **Tick each task in `tasks.md` (`- [ ]` → `- [x]`) as it completes.**
   Maintain `docs/specs/<id>/execution-log.md`: append progress and run tests
   (unit/integration per config) at logical checkpoints — self-checking as you go.
   **After each completed task: checkpoint (checkmark, log entry with a concrete Next,
   WIP committed/noted), then reset per `contextManagement.taskBoundary` (default
   `compact`); mid-task compact only, never clear; never reset without the
   checkpoint.** Same tooling as CI; logging/observability identical to runtime.

8. **Review** (`needs-review`). Run up to `reviews.selfReviewCount` self-reviews and
   `reviews.criticReviewCount` critic reviews (configured critics, e.g. a different
   harness/model) BEFORE escalating to the human reviewer. Then run the **security
   review gate** (`security.review`): the built-in security-review skill when
   available, else the-loop's checklist (`reference/security.md`); a work item at
   risk tier ≥ `security.review.humanSignOffMinTier` waits for a named human security
   sign-off. Record every review as a PR/ticket comment and in the execution log's
   review table (the security round in its Security review section). Notify per the
   `notifications.events` filters (harness-config.yaml), resolving recipients by role
   from `.the-loop/collaborators.yaml`, when a human action is pending.

9. **Complete** (`complete`). Present validated evidence that the acceptance criteria
   are met (tests, screenshots, logs) on the PR; record it in the execution log.
   **Before requesting human review, post/update the R10 reviewer briefing in the PR**
   (required gate item — `userInteraction.prSummary.required`), produced from
   `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/pr-briefing.md`: a **condensed,
   prioritized** summary saying
   **where to focus first**, **mermaid** diagram(s) of the change, and the
   spec→implementation insights + low-level decisions. Whenever you ask for input, give
   enough context to decide, and **educate the user on the low-level design decisions —
   this is mandatory, not optional.**

10. **Capture learnings.** Add to `learnings/learnings.md` (+ a `learning-<nnn>.md`) for
   any user/system feedback worth remembering. Log durable decisions under
   `docs/decisions/`.

All questions and decisions go through ticket/PR comments (paper trail). The checked-in
specs + execution log are the single record of the work.
