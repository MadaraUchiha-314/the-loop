# The loop — workflow reference

The end-to-end loop to complete a work item. Once `requirements.md`, `design.md` and
`tasks.md` are finalized and approved, the harness executes end-to-end with MINIMAL or
NO user intervention.

## The artifact chain & the iterate-until-locked rule

Every work item is a chain of artifacts, each **derived from the one before it**:

```
brainstorm.md (optional, root) → requirements.md → design.md → tasks.md → implementation
```

The core rule holds at **every** link, not just requirements: an artifact is **iterated
on with human feedback until it is locked** (`status: approved`), and only then does the
loop derive the next artifact and advance the phase. Feedback and refinement happen on
each artifact in turn; nothing downstream is written against an unlocked upstream artifact.

## Phase 0 — brainstorm (optional, the root artifact)

When work starts as a **fuzzy idea** rather than a well-formed requirement, begin with a
`brainstorm.md` scratchpad (`/the-loop:brainstorm`) — the **root artifact** the rest of
the chain grows from. It is deliberately free-form: problem/opportunity, context &
constraints, ideas & options (including rejected ones and *why*), sketches, open
questions, and a working hypothesis. Iterate it with feedback until locked, then
**convert** it to `requirements.md` (`/the-loop:new-requirement` reads the sibling
brainstorm and derives requirements from it). Everything considered-and-dropped stays in
`brainstorm.md` as the record; only the chosen direction carries forward.

**Brainstorming is optional.** A work item whose scope is already clear starts directly at
`requirements-definition` — nothing forces a brainstorm.

## Pre-conditions for a work item

A work item must have a well-defined **description**, detailed **goal**, and
**acceptance criteria** before specs begin. If missing, draft them (a `brainstorm.md` is a
good place to converge on them) and confirm via a ticket comment.

## The 3-phase spec (Kiro-style — https://kiro.dev/docs/specs/)

Stored in `<workflow.specDir>/<id>/` (default `docs/specs/<id>/`). Each phase ends with
a **human review** (`workflow.requireHumanReviewPerPhase`, default true). Do not advance
until the current phase is approved; record the approver (paper trail).

1. **`requirements.md`** (or **`bugfix.md`** for bugs) — introduction, user stories, and
   acceptance criteria in **EARS** notation
   (`WHEN <event> THEN the system SHALL <response>`). Phase: `requirements-definition`.
2. **`design.md`** — overview, architecture, components/interfaces, data models, error
   handling, testing strategy. Derived from approved requirements. Phase: `design`.
3. **`tasks.md`** — a **DAG** of small, verifiable tasks. Each task references the
   requirement(s) it satisfies and declares dependencies. Phase: `tasks-breakdown`.

## Phase state machine (tracked on the ticket via labels)

Label = `<workflow.phaseLabelPrefix><phase>` (e.g. `loop:design`). Keep the label in
sync at every transition and mirror it in the execution log's `phase` front-matter.

```
not-started → brainstorming → requirements-definition → design → tasks-breakdown
            → implementation → needs-review → complete
```

`brainstorming` is **optional**: a work item either enters it (when it needs a scratchpad)
or transitions straight from `not-started` to `requirements-definition`.

`/the-loop:init` creates the labels; `/the-loop:work-on` drives all the transitions
end-to-end. The same transitions are also exposed as **granular commands** (`work-on` is
their superset), one per step:

| Step | Command | Phase entered |
|------|---------|---------------|
| Brainstorm a fuzzy idea (optional, pre-ticket) | `brainstorm <title>` | brainstorming |
| Draft requirements (pre-ticket, temp folder; converts a brainstorm if present) | `new-requirement <title>` | requirements-definition |
| Create the ticket; promote `draft-<slug>/` → `docs/specs/<id>/` | `create-ticket <path>` | requirements-definition |
| Requirements → design | `create-design <id>` | design |
| Requirements + design → tasks DAG | `create-tasks-plan <id>` | tasks-breakdown |
| Implement, self-check, self/critic-review | `execute-tasks <id>` | implementation → needs-review |
| Cleanup after all tasks (close ticket; extensible) | `finish-tasks <id>` | complete |
| Read-only status report | `work-status <id>` | — |

`brainstorm`/`new-requirement`/`create-ticket` support the case where work starts as an
idea: optionally brainstorm it, define requirements (from the brainstorm or fresh), then
mint the ticket from them.

## Link artifacts to the ticket (single source of truth)

Once each spec document is established (requirements, design, tasks), **update the work
item (GitHub issue / Jira) with a reference (link) to the checked-in artifact** — not a
copy of its contents. The checked-in file is the single source of truth.

- Reference, don't duplicate: link to `docs/specs/<id>/{requirements,design,tasks}.md`.
- **Subsequent changes to a spec doc happen as EDITS to that file (and, where the ticket
  embeds a summary, an edit to that comment/description) — NOT as new comments.** This
  keeps one canonical version and a clean history.

## Implementation & self-checking

- Execute the task DAG in dependency order (`implementation`).
- **Test-first discipline** (`tdd.mode`): the invariant is **no production code without a
  failing test that motivates it**. `standard` = red→green→refactor per task;
  `tdd-first` = all tests for the work item written and failing before any production
  code; `off` = not enforced. Each task's checkpoint in the execution log records the
  **test command and its red→green transition** as evidence — "did a test fail first?"
  is a recorded fact, not an assumption.
- **Keep `tasks.md` checkmarks current**: as each task is completed, tick its `- [ ]` →
  `- [x]` so the ticket/spec always shows what is done vs. outstanding.
- Maintain `docs/specs/<id>/execution-log.md` (checked in): append progress, and **run
  tests at logical checkpoints** — self-checking as you go.
- Use the configured tooling (see `tooling.md`); same commands as CI.
- Apply the **minimalism** ladder (see `minimalism.md`) to avoid generating bloat — least
  code that correctly does the job; justify any new dependency in `design.md`.

## Self-review & critic-review (before a human)

- After the work is done, run **self-reviews** then **critic reviews** using configured
  critics — a *different* harness/model (e.g. Cursor + GPT‑5.5 reviewing Claude Opus
  output). `reviews.selfReviewCount` / `reviews.criticReviewCount` (default **3**) are
  caps run BEFORE reaching out to the human reviewer (`needs-review`).
- **The procedure is defined in `reviewing.md`** — attribution prefixes, reply-first-
  then-fix, one-finding-per-commit, stop-on-zero-new-findings, and the diminishing-
  returns escalation. Follow it so review depth is reproducible and the loop converges.
- **All reviews happen as comments** in the PR and/or ticket (paper trail). Record every
  round in the execution log's review table.

## Evidence, the ready-to-ship gate & risk-tiered autonomy

At the end, present **validated evidence** that the work item meets the acceptance
criteria (test output, screenshots, logs).

Before requesting human review or any autonomous completion, the **ready-to-ship gate**
must ALL hold:

- green checks;
- **all review threads resolved**;
- validated evidence recorded; **and**
- the **R10 reviewer briefing** is posted/updated in the PR — a condensed, prioritized
  summary (where to focus), mermaid diagram(s), and the low-level decisions — produced
  from `userInteraction.prSummary.templatePath` (default
  `.the-loop/templates/pr-briefing.md`). This is the **trigger** that makes mandatory
  user-education actually fire (`userInteraction.prSummary.required`, default true); do
  not request review without it. RULE: educating the reviewer is not optional.

Then the loop marks the work item ready and applies **risk-tiered autonomy**
(`config.autonomy`):

- Each work item has a **risk tier 1–5** (from its front-matter `riskTier`, else
  `autonomy.defaultTier`; raised automatically when the change touches
  `autonomy.sensitivePaths` — auth/security/schema/public API — if `inferFromChange`).
- `autonomy.tiers` maps each tier to a gate: `autonomous-complete` (finish after the
  review loop), `human-approves-pr`, or `human-approves-spec-and-pr`. Only tiers the
  policy permits complete without a human; the rest wait for the named approval.

This makes autonomy safe-by-construction: a typo fix (low tier) can complete on its own,
while an auth/payments change (high tier) always waits for a human — one meaningful
signal instead of a firehose of approvals. Then move to `complete`.

## Resumability

Because the specs and execution log are checked in, the-loop can resume a work item
exactly where it left off — read the execution log's `phase` and the specs' `status`,
and continue.

## DAG orchestration across work items

When an entire project is broken into work items, the-loop orchestrates them as a DAG
using dependency relationships:
- Jira: `blocked by` / `depends on` fields.
- GitHub: issue task-lists / linked issues / sub-issues (and Projects) — confirm and
  record the chosen mechanism.

## Interacting with the rest of the harness

the-loop may freely use other MCP tools, skills and plugins available in the harness
(e.g. Jira via MCP, GitHub via `gh`, plugins like ponytail/superpowers). The user
registers what to be aware of in `.the-loop/external-tools.md`
(or `externalTools.notes`). See `collaboration.md`.

## Predictability & guarantees (open design question)

Much of this is a fixed PDLC process; the harness should not re-derive it each time.
Candidate mechanisms to make steps predictable/guaranteed:
- **Harness hooks** (this plugin's `hooks/` in Claude Code; the always-applied rule in
  `rules/` in Cursor) to force steps to run.
- **Custom code** where hooks are insufficient.
This is an open question — evaluate and record a decision as it firms up.
