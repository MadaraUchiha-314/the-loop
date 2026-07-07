# Capability: spec-workflow

> The core loop: a work item is specified as a chain of artifacts — optional brainstorm,
> then a Kiro-style 3-phase spec — each iterated with human feedback until locked, then
> executed end-to-end with minimal intervention.

## What it is

The product-development-lifecycle workflow the-loop runs on every work item, exposed as
the `/the-loop:work-on` superset command and granular per-step commands
(`brainstorm`, `new-requirement`, `create-ticket`, `create-design`, `create-tasks-plan`,
`execute-tasks`, `finish-tasks`, `work-status`).

## Current behaviour

- Every work item SHALL have a ticket; nothing is worked without one.
- A work item's spec SHALL live in `docs/specs/<id>/` as the artifact chain
  `brainstorm.md (optional) → requirements.md|bugfix.md → design.md → tasks.md`, plus
  `execution-log.md`.
- Each artifact SHALL be iterated with feedback until **locked** (`status: approved`);
  no downstream artifact is written against an unlocked upstream one
  (`workflow.requireHumanReviewPerPhase`, default true).
- WHEN a work item starts as a fuzzy idea THEN the loop SHALL begin with a
  `brainstorm.md` root artifact (optional Phase 0) and convert it to requirements once
  locked.
- The work item's phase SHALL be tracked on the ticket via labels
  (`<workflow.phaseLabelPrefix><phase>`) through the state machine
  `not-started → brainstorming (optional) → requirements-definition → design →
  tasks-breakdown → implementation → needs-review → complete`, mirrored in the
  execution log.
- `tasks.md` SHALL be a DAG of small verifiable tasks referencing requirements;
  checkmarks are kept current during implementation.
- Completion SHALL be gated by the ready-to-ship gate (green checks, threads resolved,
  evidence, PR briefing, capability docs folded in) and risk-tiered autonomy
  (`config.autonomy`).

## Design

[`reference/workflow.md`](../../skills/the-loop/reference/workflow.md) ·
[`SKILL.md`](../../skills/the-loop/SKILL.md) ·
[architecture § the loop](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-25 | Added the capability-docs fold-in as a ready-to-ship gate item | [spec](../specs/issue-25/), [decision-020](../decisions/decision-020.md) |
| issue-18 | Design phase gained first-class UI/UX design artifacts | [spec](../specs/issue-18/), [decision-018](../decisions/decision-018.md) |
| issue-17 | Added the optional brainstorming phase and the iterate-until-locked rule as a first-class principle | [spec](../specs/issue-17/), [decision-017](../decisions/decision-017.md) |
| issue-1 | Established the 3-phase Kiro-style spec workflow, phase labels, granular commands and templates (v0) | [spec](../specs/issue-1/), [decision-004](../decisions/decision-004.md), [decision-011](../decisions/decision-011.md) |
