---
type: requirements
phase: requirements-definition
workItem: issue-17
status: approved
approvedBy: ["@MadaraUchiha-314 (issue #17 as authored)"]
collaborators: [product-manager, architect]
overrides: {}
---

# Requirements: a brainstorm phase and `/brainstorm` command

> **Source of truth:** GitHub [issue #17](https://github.com/MadaraUchiha-314/the-loop/issues/17).
> Derived from the locked [`brainstorm.md`](brainstorm.md). Design and the task DAG live
> in `design.md` and `tasks.md`.

## Introduction

Add an **optional brainstorming phase** to the-loop whose deliverable — `brainstorm.md` —
is the **root artifact** every later artifact derives from. Give it a `/brainstorm`
command, a template, a place in the phase state machine, and a conversion path into
`requirements.md`. Generalize the loop's core idea so it reads the same at every link:
each artifact is iterated on with feedback until locked, then the loop advances.

New chain: `brainstorm (optional) → requirements → design → tasks → implementation`.

## Requirements

### R1 — brainstorm.md root artifact & template

**User story:** As a product-manager exploring a fuzzy idea, I want a free-form
`brainstorm.md` scratchpad, so that I can converge on a direction before committing to
requirements.

#### Acceptance criteria (EARS)

1. WHEN the plugin is installed THEN it SHALL provide a `.the-loop/templates/brainstorm.md`
   template with front-matter (`type: brainstorm`, `phase: brainstorming`, `status`,
   `approvedBy`, `collaborators`) and free-form sections (problem, options, open questions,
   working hypothesis, hand-off).
2. The template SHALL be listed in `.the-loop/manifest.yaml` as a managed template and as
   an **optional** per-work-item artifact (`spec-brainstorm`, phase `brainstorming`).

### R2 — `/brainstorm` command

**User story:** As a user, I want a `/the-loop:brainstorm <title>` command, so that I can
start a brainstorm without a ticket.

#### Acceptance criteria (EARS)

1. WHEN `/the-loop:brainstorm <title>` is run THEN it SHALL create (or reuse)
   `docs/specs/draft-<slug>/` and write `brainstorm.md` from the template.
2. The command SHALL instruct the user to iterate the brainstorm with feedback until it is
   **locked** (`status: approved`) and then point to `/the-loop:new-requirement` as the
   conversion step.

### R3 — convert brainstorm → requirements

**User story:** As a user, I want a locked brainstorm to become requirements, so that the
chosen direction carries forward without re-typing it.

#### Acceptance criteria (EARS)

1. WHEN `/the-loop:new-requirement` runs and a sibling `brainstorm.md` exists THEN it SHALL
   derive `requirements.md` from the brainstorm's locked direction.
2. IF the sibling `brainstorm.md` is not `approved` THEN the command SHALL NOT convert it
   (lock it first).
3. WHEN `/the-loop:create-ticket` promotes a `draft-<slug>/` folder THEN it SHALL carry any
   `brainstorm.md` along and update its front-matter `workItem`.

### R4 — phase state machine includes optional brainstorming

**User story:** As the harness, I want `brainstorming` in the phase state machine, so that
a work item's phase can reflect it.

#### Acceptance criteria (EARS)

1. The `workflow.phases` schema enum and default SHALL include `brainstorming` between
   `not-started` and `requirements-definition`, and both shipped `config.yaml` files SHALL
   list it.
2. Documentation SHALL state that `brainstorming` is **optional** — a well-defined work
   item may transition straight from `not-started` to `requirements-definition`.

### R5 — the iterate-until-locked rule is generalized

**User story:** As a contributor, I want the "feedback + iteration per artifact, advance
only when locked" idea stated once, so that it applies uniformly across phases.

#### Acceptance criteria (EARS)

1. The skill (`SKILL.md`), `reference/workflow.md`, `work-on` and `README.md` SHALL state
   that every artifact — from the `brainstorm.md` root onward — is iterated with feedback
   until locked (`status: approved`) before the next artifact is derived.

## Non-functional requirements

- **Backwards compatible & additive.** Existing work items without a `brainstorm.md` are
  unaffected and continue to start at requirements.
- **Docs lint clean.** All new/changed markdown passes `markdownlint`.
- **Config valid.** `config.yaml` continues to validate against `config.schema.json`.

## Out of scope

- Automating brainstorm→requirements distillation quality (it remains an agent task).
- Any CLI (`the_loop`) code changes — this work item is plugin docs/templates/commands.
- Creating the `loop:brainstorming` label in live ticketing (handled by `/init` at
  scaffold time, not this change).

## Open questions

None — resolved in `brainstorm.md`.
