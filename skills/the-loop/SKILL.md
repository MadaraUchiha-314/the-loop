---
name: the-loop
description: The operating model for delivering product work items end-to-end. Use whenever working a ticket/issue with the-loop — to plan, execute, self/critic-review, escalate, and record decisions and learnings under the project's PDLC rules.
---

# the-loop

"the-loop" is an opinionated product-development-lifecycle (PDLC) harness. Once the
3-phase spec (requirements → design → tasks) is approved, the harness executes a work
item end-to-end with minimal or no human intervention, escalating only when a decision
is genuinely required.

## The 3-phase spec workflow (Kiro-style)

Every non-trivial work item is specified in three phases, each gated by a human review
(https://kiro.dev/docs/specs/). Specs live in `docs/specs/<id>/`:

1. **`requirements.md`** (or **`bugfix.md`** for bugs) — user stories + EARS acceptance
   criteria. Phase label: `requirements-definition`.
2. **`design.md`** — architecture, components, data models, error handling, testing
   strategy. Phase label: `design`.
3. **`tasks.md`** — a DAG of small, verifiable tasks referencing requirements. Phase
   label: `tasks-breakdown`.

The work item's **phase** is tracked on the ticket via a label
(`<phaseLabelPrefix><phase>`) and mirrored in the execution log. The state machine:

`not-started → requirements-definition → design → tasks-breakdown → implementation → needs-review → complete`

## Operating principles (rules)

- **Every work item has a ticket.** Nothing the harness works on lacks a GH issue (or
  Jira) ticket.
- **Spec before execution.** The 3-phase spec under `docs/specs/<id>/` is created and
  each phase reviewed/approved by the required collaborators before code is written.
- **Human review per phase.** A human approves at the end of requirements, design and
  tasks (`workflow.requireHumanReviewPerPhase`, default true).
- **Identify collaborators up-front.** Each work item names the personas it needs
  (architect, designer, PM, engineer, QA…). Not every task needs every persona. More
  can be added later.
- **Paper trail.** Every decision/opinion from a human is captured on the ticket or
  the PR. Planning questions → ticket comments. PR review → PR comments/replies.
- **Self-check continuously.** Maintain `docs/specs/<id>/execution-log.md`; keep the
  phase label in sync; run tests at logical checkpoints; log progress for visibility.
- **Review before escalating.** Run configured self-reviews then critic reviews
  (a different harness/model) before reaching out to a human reviewer. All reviews are
  comments on the PR/ticket.
- **Evidence at the end.** Present validated evidence that acceptance criteria are met.
- **Same tooling everywhere.** Local checks and CI use identical tooling — no
  last-minute CI surprises.
- **Identical observability.** Logging is the same at dev-time and runtime; the only
  dev advantage is breakpoints.

## Configuration

The project's behaviour is driven by `.the-loop/config.yaml`, validated against
`.the-loop/config.schema.json`. A subset of keys can be overridden per work item via
the YAML front-matter `overrides` of the work-item / spec markdown. Files the loop
manages are listed in `.the-loop/manifest.yaml`.

## Commands

- `/the-loop:init` — scaffold the-loop into a repo.
- `/the-loop:work-on <ticket>` — run the loop on a work item (resumable).
- `/the-loop:upgrade-the-loop` — reconcile project files with the plugin version.

## Knowledge the loop maintains

- `docs/architecture/architecture.md` — architecture index → sub-component docs.
- `docs/decisions/decisions.md` + `decision-<nnn>.md` — decision log.
- `learnings/learnings.md` + `learning-<nnn>.md` — learnings from user & system
  feedback, checked in for review.

## External tools

The harness may freely use the MCP servers, CLIs, skills and plugins registered in
`.the-loop/external-tools.md` (or `externalTools.notes` in config).
