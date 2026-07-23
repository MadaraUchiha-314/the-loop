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

## UI/UX design

> Only for work items with a **user-facing surface** (skip for backend/CLI/infra — write
> `N/A`). Architecture/HLD/LLD stays above in markdown + mermaid; the **visual** design is
> tracked as first-class artifacts — Figma links and/or self-contained HTML+CSS+JS
> prototypes (Claude-artifact style) — under `<specDir>/<id>/design/`
> (`design.uiArtifacts.dir`). Iterate each with the **designer** until locked
> (`status: approved`), exactly like every other artifact. See `reference/design-artifacts.md`.

| Artifact | Type | Location / link | Covers (screen · requirement) | Status |
|----------|------|-----------------|-------------------------------|--------|
| `design/<screen>.html` | html-prototype | `design/<screen>.html` | <Screen> · R<n> | draft |
| Figma — <flow> | figma | https://figma.com/file/… | <Flow> · R<n> | draft |

- **Flows & states:** the screens/states covered and the transitions between them.
- **Design system / tokens:** colours, type, spacing, components reused (link the source).
- **Accessibility & responsiveness:** target breakpoints, keyboard/contrast intent.
- **Evidence:** rendered screenshots of the **locked** artifacts (`design.uiArtifacts.screenshotEvidence`).

## Data models

Schemas, types, persistence. (Link `.the-loop/config.schema.json`-style schemas if any.)

## Error handling

Failure modes and how they are surfaced (observability identical at dev-time/runtime).

## Security design

> How each trust boundary from the requirements' **Security considerations** is
> enforced — mechanisms, not intentions (`security.design.required`, default true).
> A boundary left unenforced fails this phase's gate. See `reference/security.md`.

- **AuthN/AuthZ:** who is identified how; where authorization is checked.
- **Input validation & injection surfaces:** every untrusted ingress and its
  validation/encoding; SQL/command/path/prompt injection surfaces named explicitly.
- **Secrets handling:** where secrets come from (env/secret store — never repo/logs).
- **Least privilege:** minimum permissions/scopes each component runs with.
- **Fail-closed behaviour:** the concrete response when a check cannot be made.
- **Abuse-case coverage:** each abuse case → the mechanism defeating it → the negative
  test proving it (feeds the testing strategy below).

## Testing strategy

How requirements map to unit/integration tests, and what evidence proves acceptance.
Name the integration scenarios by their Gherkin `Scenario:` titles (each test's
docstring links back here via `Requirement:`); for API work, link the OpenAPI/SDL
contract files under `specs/`. See `reference/testing.md`.

## Trade-offs & decisions

Significant choices made here; log durable ones under `docs/decisions/`.

## Open questions

Raised as ticket comments and linked here.
