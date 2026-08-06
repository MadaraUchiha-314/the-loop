---
type: design
phase: design
workItem: ""
status: draft                # draft | in-review | approved
approvedBy: []
overrides: {}
---

<!-- Written per the `the-loop:writing` skill: front-load each section's
     conclusion, draw it rather than describe it (3+ named parts -> a mermaid
     diagram), and keep the formal registers formal (EARS, abuse cases,
     RFC-2119, API contracts, schema descriptions). No length limit — length
     follows the change; the test is whether a sentence can come out without
     losing information. A gated section stays even when it is empty. -->

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

## Module structure

> **Where the delivered code will land.** The reviewer has just read what the components
> are; this says which files, modules and packages the work item creates, changes or
> removes, before any of them exist. Scoped to **this work item's delta** — the standing
> view is `docs/architecture/architecture.md`, and repeating it here buries the change.
> Not a second *Components & interfaces*: that section carries responsibility and
> contract, this one carries **placement**.

```text
<repo>/
├── <path/to/new/module>         new       <one line: what lives here>
├── <path/to/changed/module>     changed   <one line: what changes>
└── <path/to/removed/module>     removed   <one line: what replaces it>
```

| Path | Responsibility | Status | Requirement |
|------|----------------|--------|-------------|
| `<path>` | <one line> | new \| changed \| removed | R<n> |

Draw the dependency direction when three or more of these modules depend on one another
(`userInteraction.writingStyle.diagramFirst`) — a mermaid graph of who imports whom, which
is the part a reviewer argues with.

**A work item that changes no code** (docs-only, process-only) says so in one sentence and
names the files it does change. The section stays: a gated section is never deleted to
shorten a document.

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

Schemas, types, persistence. (Link `.the-loop/harness-config.schema.json`-style schemas if any.)

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

The strategy **in a paragraph**: how requirements map to unit/integration tests, which
contracts are involved (for API work, link the OpenAPI/SDL files under `specs/`), and
what evidence proves acceptance. Name the integration scenarios by their Gherkin
`Scenario:` titles (each test's docstring links back here via `Requirement:`).

The **executable detail** — which testing types apply and which are `n/a` and why, the
verification environment, the evidence to capture — belongs to `testing-plan.md`, derived
from this design at the `test-planning` node and executed at `verification`. Do not
duplicate it here. See `reference/testing.md`.

## Trade-offs & decisions

Significant choices made here; log durable ones under `docs/decisions/`.

## Open questions

Raised as ticket comments and linked here.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
