---
type: design
phase: design
workItem: ""
status: draft                # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Design: <work item title>

> Phase 2 of 3 (requirements → design → tasks). Derives from the approved
> requirements. MUST be reviewed and approved before moving to tasks breakdown.

## Overview

The technical approach at a glance and how it satisfies the requirements.

## Architecture

Key components and how they interact. Reference `docs/architecture/architecture.md`
and add sub-component docs if needed. Include diagrams where helpful.

## Components & interfaces

For each component: responsibility, inputs/outputs, public interface/contract.

## Data models

Schemas, types, persistence. (Link `.the-loop/config.schema.json`-style schemas if any.)

## Error handling

Failure modes and how they are surfaced (observability identical at dev-time/runtime).

## Testing strategy

How requirements map to unit/integration tests, and what evidence proves acceptance.
Name the integration scenarios by their Gherkin `Scenario:` titles (each test's
docstring links back here via `Requirement:`); for API work, link the OpenAPI/SDL
contract files under `specs/`. See `reference/testing.md`.

## Trade-offs & decisions

Significant choices made here; log durable ones under `docs/decisions/`.

## Open questions

Raised as ticket comments and linked here.
