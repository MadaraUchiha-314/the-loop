# The loop — workflow reference

The end-to-end loop to complete a work item. Once `requirements.md`, `design.md` and
`tasks.md` are finalized and approved, the harness executes end-to-end with MINIMAL or
NO user intervention.

## Pre-conditions for a work item

A work item must have a well-defined **description**, detailed **goal**, and
**acceptance criteria** before specs begin. If missing, draft them and confirm via a
ticket comment.

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
not-started → requirements-definition → design → tasks-breakdown
            → implementation → needs-review → complete
```

`/the-loop:init` creates the labels; `/the-loop:work-on` drives the transitions.

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
- **Keep `tasks.md` checkmarks current**: as each task is completed, tick its `- [ ]` →
  `- [x]` so the ticket/spec always shows what is done vs. outstanding.
- Maintain `docs/specs/<id>/execution-log.md` (checked in): append progress, and **run
  tests at logical checkpoints** — self-checking as you go.
- Use the configured tooling (see `tooling.md`); same commands as CI.

## Self-review & critic-review (before a human)

- After the work is done, do a **self-review**.
- Then run **critic reviews** using configured critics — a *different* harness/model
  (e.g. Cursor + GPT‑5.5 reviewing Claude Opus output).
- Run **X** self-reviews and **X** critic reviews (configurable;
  `reviews.selfReviewCount` / `reviews.criticReviewCount`, default **3**) BEFORE
  reaching out to the human reviewer (`needs-review`).
- **All reviews happen as comments** in the PR and/or ticket (paper trail). Record them
  in the execution log's review table.

## Evidence & completion

At the end, present **validated evidence** that gives the user confidence the work item
meets the acceptance criteria (test output, screenshots, logs). Then move to
`complete`.

## Resumability

Because the specs and execution log are checked in, the-loop can resume a work item
exactly where it left off — read the execution log's `phase` and the specs' `status`,
and continue.

## DAG orchestration across work items (the dream)

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
- **Claude hooks** (this plugin's `hooks/`) to force steps to run.
- **Custom code** where hooks are insufficient.
This is an open question from issue #1 — evaluate and record a decision as it firms up.
