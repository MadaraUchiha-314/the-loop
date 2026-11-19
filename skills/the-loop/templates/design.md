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
> requirements, and is reviewed with `testing-plan.md` at the `design-approval` gate.
>
> **Stay at the level of decisions.** This file holds the interfaces, the architecture
> and the technology choices. It carries no function or method names, signatures,
> class layouts, algorithms, code snippets, internal data structures or file-by-file
> change lists: that detail belongs in `tasks.md` and the code.

## The short version

<!-- The card: what changes, why, and what to check. About 120 words is the
     guide, not a limit. Point the reviewer at Interfaces, and add or link a
     diagram when the change has three or more named parts. -->

What changes and why, in a few plain sentences, and where the reviewer should start.

## Interfaces

Everything an outside party relies on, one topic per subsection. For a topic this
change leaves alone, write one line, "No change", rather than dropping it.

- **CLI:** commands, flags and their output.
- **Configuration:** keys, defaults and validation.
- **API and schema:** endpoints, events, message formats.
- **Persisted formats:** files and records written to disk or a store.
- **User-visible behaviour:** what a person sees, including how failures surface.

## Architecture

The components, how they connect and how data moves between them, with at least one
mermaid diagram. Say why the pieces are arranged this way. Reference
`docs/architecture/architecture.md` and add sub-component docs if needed.

## Technology choices

| Choice | Chosen | Alternatives | Why |
|---|---|---|---|
| <a library, storage format, protocol or pattern> | <the choice> | <what else was considered> | <why this one won> |

Log a durable choice under `docs/decisions/`.

## UI/UX design

> Only for work items with a **user-facing surface** (skip for backend/CLI/infra — write
> `N/A`). Architecture/HLD/LLD stays above in markdown + mermaid; the **visual** design is
> tracked as first-class artifacts — Figma links and/or self-contained HTML+CSS+JS
> prototypes (Claude-artifact style) — under `<specDir>/<id>/design/`
> (`design.uiArtifacts.dir`). Iterate each with the **designer** until the designer is
> satisfied; this document itself is locked at the `design-approval` gate (issue-281).
> See `reference/design-artifacts.md`.

| Artifact | Type | Location / link | Covers (screen · requirement) | Status |
|----------|------|-----------------|-------------------------------|--------|
| `design/<screen>.html` | html-prototype | `design/<screen>.html` | <Screen> · R<n> | draft |
| Figma — <flow> | figma | https://figma.com/file/… | <Flow> · R<n> | draft |

- **Flows & states:** the screens/states covered and the transitions between them.
- **Design system / tokens:** colours, type, spacing, components reused (link the source).
- **Accessibility & responsiveness:** target breakpoints, keyboard/contrast intent.
- **Evidence:** rendered screenshots of the **locked** artifacts (`design.uiArtifacts.screenshotEvidence`).

## Security design

> How each trust boundary from the requirements' **Security considerations** is
> enforced — mechanisms, not intentions (always required).
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

## Open questions

Raised as ticket comments and linked here.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
