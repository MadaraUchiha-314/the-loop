# Learning 001: A broad vision issue must be decomposed before execution

- **Date:** 2026-06-27
- **Source:** system-feedback
- **Work item:** issue-1

## What happened
Issue #1 is a full product vision, not a single deliverable. Trying to implement every
section at once would produce an unreviewable change and violate the-loop's own rule
that work items have clear, testable acceptance criteria.

## Learning
When a ticket is an epic-shaped vision, the-loop should first establish its own
skeleton/contracts, record the scoping decision, and spin the remaining sections out as
child work items with explicit dependencies — rather than attempting a monolithic pass.

## Action
- Delivered a v0 skeleton (see decision-003) and recorded the deferral.
- Follow-up: open child issues for webhooks, remote execution, DAG orchestration, and
  per-language tooling integrations, linked back to issue #1 as an epic.
