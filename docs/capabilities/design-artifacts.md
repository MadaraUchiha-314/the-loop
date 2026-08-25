# Capability: design-artifacts

> UI/UX design as a first-class, tracked artifact of the design phase — Figma links
> and/or self-contained HTML prototypes, iterated with the designer until they sign off.

## What it is

For user-facing work items, `design.md` (markdown + mermaid) is the wrong medium for
*visual* design. This capability tracks the visual design as reviewable artifacts that
become the contract the implementation must match.

## Current behaviour

- WHEN a work item has a user-facing surface THEN the design phase SHALL track UI/UX
  design artifacts under `docs/specs/<id>/design/` (`design.uiArtifacts.dir`),
  inventoried in `design.md`; backend/CLI/infra work records `N/A`.
- Artifacts SHALL be Figma links and/or **self-contained** HTML+CSS+JS prototypes
  (`design.uiArtifacts.format`, `selfContained: true` — no external network deps).
- Artifacts SHALL be iterated with the **designer** persona on the *rendered* output
  until the designer signs off — recorded as a row-level `approved` in `design.md`'s
  inventory, while the chain's front-matter locks stay with the approval gates
  (issue-281).
- WHEN the designer signs an artifact off THEN rendered screenshots SHALL be captured
  as evidence (`design.uiArtifacts.screenshotEvidence`).

## Design

[`reference/design-artifacts.md`](../../skills/the-loop/reference/design-artifacts.md) ·
[`docs/specs/issue-18/design.md`](../specs/issue-18/design.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-18 | Made UI/UX design artifacts first-class design-phase artifacts with the designer iteration loop | [spec](../specs/issue-18/), [decision-018](../decisions/decision-018.md) |
