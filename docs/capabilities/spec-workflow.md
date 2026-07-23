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
- **Security SHALL be a gated concern of each phase** (`config.security`):
  requirements/bugfix carry a Security considerations threat-model-lite (untrusted
  actors, trust boundaries, abuse cases, fail-closed — "no new attack surface" is
  written and justified, never implied); design carries a Security design section
  enforcing every boundary; security-relevant tasks name the negative test proving the
  boundary holds.
- Completion SHALL be gated by the ready-to-ship gate (green checks, threads resolved,
  evidence, **a passed security review** — built-in security-review skill or the-loop's
  checklist per `security.review.mechanism` — PR briefing, capability docs folded in)
  and risk-tiered autonomy (`config.autonomy`); an effective risk tier ≥
  `security.review.humanSignOffMinTier` (default 4) SHALL wait for a named human
  security sign-off, and an unresolved security finding SHALL block completion at any
  tier.
- The loop SHALL manage its context window by **checkpoint-then-reset**
  (`config.contextManagement`): a reset (clear or compact) is always preceded by a
  checkpoint — `tasks.md` checkmarks current, an execution-log entry with a concrete
  next step, the phase label in sync, WIP committed or noted.
- WHEN the phase advances across a locked artifact (most importantly
  tasks-breakdown → implementation) THEN the loop SHALL reset per
  `contextManagement.phaseBoundary` (default `clear`) and derive the next phase's work
  from the checked-in artifacts, not the conversation.
- WHEN a task in the DAG completes THEN the loop SHALL checkpoint and reset per
  `contextManagement.taskBoundary` (default `compact`); mid-task only compaction is
  permitted (`midTask`), never clearing. Headless sessions reset by ending at the
  boundary and resuming fresh via the execution log.

## Design

[`reference/workflow.md`](../../skills/the-loop/reference/workflow.md) ·
[`reference/context.md`](../../skills/the-loop/reference/context.md) ·
[`reference/security.md`](../../skills/the-loop/reference/security.md) ·
[`SKILL.md`](../../skills/the-loop/SKILL.md) ·
[architecture § the loop](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-48 | Added checkpoint-then-reset context-window management (clear at phase boundaries, compact at task boundaries, `contextManagement` config) | [spec](../specs/issue-48/), [decision-027](../decisions/decision-027.md) |
| issue-47 | Security became a gated concern of every phase: threat-model-lite in requirements, Security design section, security-review gate item, risk-tiered human sign-off (`config.security`) | [spec](../specs/issue-47/), [decision-026](../decisions/decision-026.md) |
| issue-25 | Added the capability-docs fold-in as a ready-to-ship gate item | [spec](../specs/issue-25/), [decision-020](../decisions/decision-020.md) |
| issue-18 | Design phase gained first-class UI/UX design artifacts | [spec](../specs/issue-18/), [decision-018](../decisions/decision-018.md) |
| issue-17 | Added the optional brainstorming phase and the iterate-until-locked rule as a first-class principle | [spec](../specs/issue-17/), [decision-017](../decisions/decision-017.md) |
| issue-1 | Established the 3-phase Kiro-style spec workflow, phase labels, granular commands and templates (v0) | [spec](../specs/issue-1/), [decision-004](../decisions/decision-004.md), [decision-011](../decisions/decision-011.md) |
