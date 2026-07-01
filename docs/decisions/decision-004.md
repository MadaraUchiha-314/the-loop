# Decision 004: Adopt Kiro's 3-phase spec workflow for the loop

- **Status:** accepted
- **Date:** 2026-06-30
- **Deciders:** @MadaraUchiha-314 (via issue #1 update)
- **Work item:** issue-1

## Context

Issue #1 was updated to borrow Kiro's spec methodology
(https://kiro.dev/docs/specs/). The original single "delivery plan" is replaced by a
structured, phased specification with a human review gate at the end of each phase, and
an explicit phase state machine tracked on the ticket.

## Decision

- Replace `delivery-plan.md` with a 3-phase spec per work item, stored in
  `docs/specs/<id>/`:
  1. `requirements.md` (user stories + EARS acceptance criteria) — or `bugfix.md` for bugs,
  2. `design.md` (architecture, components, data models, error handling, testing),
  3. `tasks.md` (a DAG of small, verifiable tasks referencing requirements).
- A human review/approval is required at the end of each phase
  (`workflow.requireHumanReviewPerPhase`, default true).
- Track the work item's phase via labels in the ticketing system using the state
  machine `not-started → requirements-definition → design → tasks-breakdown →
  implementation → needs-review → complete`. `/init` creates the labels;
  `/work-on` keeps them in sync and mirrors the phase in the execution log.
- The execution log moves alongside the spec at `docs/specs/<id>/execution-log.md`.

## Consequences

- Clearer separation of "what / how / steps", each independently reviewable.
- The ticket reflects live progress through phase labels.
- `/work-on` becomes resumable per phase.
- Supersedes the delivery-plan portion of decision-003's v0 scope.

## Alternatives considered

- Keep the single delivery-plan — rejected: the updated issue explicitly adopts the
  Kiro 3-phase approach with per-phase human review.
