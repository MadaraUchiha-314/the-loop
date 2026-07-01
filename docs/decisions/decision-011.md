# Decision 011: Expose granular per-phase commands (with /work-on as superset)

- **Status:** accepted
- **Date:** 2026-07-01
- **Deciders:** @MadaraUchiha-314 (PR #2 review)
- **Work item:** issue-1

## Context

`/work-on` drives the whole loop end-to-end, but sometimes you want to run a single phase,
or start work **before a ticket exists** (define requirements first, mint the ticket from
them). PR #2 review proposed a set of finer-grained commands.

## Decision

Expose the loop as granular commands, each mapping to one phase transition, with
`/work-on` remaining their **superset**:

- `new-requirement <title>` — draft `requirements.md` in a temporary
  `docs/specs/draft-<slug>/` folder (no ticket yet).
- `create-ticket <path>` — create the ticket from a `requirements.md`; promote
  `draft-<slug>/` → `docs/specs/<id>/` and link the spec on the ticket.
- `create-design <id>` — requirements → `design.md` (Phase 2).
- `create-tasks-plan <id>` — requirements + design → `tasks.md` DAG (Phase 3).
- `execute-tasks <id>` — implement the DAG, self-check, self/critic-review, evidence.
- `finish-tasks <id>` — cleanup after all tasks (currently: close the ticket;
  intentionally **extensible**).
- `work-status <id>` — **read-only** status from the specs, task checkmarks and log.

Conventions:
- **Draft folder:** `docs/specs/draft-<slug>/` marks a spec with no ticket yet;
  `create-ticket` renames it to `docs/specs/<id>/`.
- Each command reuses the same skill/reference rules (reviews, paper trail, phase labels,
  `userInteraction`) — the commands are thin phase entry points, not a second workflow.

## Consequences

- Supports incremental, human-in-the-loop use and the "requirements before ticket" flow.
- `work-on` stays the one-shot path; the granular commands share its behavior, so there is
  one workflow with two granularities (no divergence).
- `finish-tasks` gives cleanup a single home to grow (branch archival, release, notify).

## Alternatives considered

- **Only `/work-on`** — rejected: no way to run a single phase or start pre-ticket.
- **Separate workflow for the granular commands** — rejected: would risk drift; instead
  they delegate to the same skill/reference rules.
