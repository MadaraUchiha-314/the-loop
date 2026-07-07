# Capability: design-artifacts

> UI/UX design as a first-class, tracked artifact of the design phase — Figma links
> and/or self-contained HTML prototypes, iterated with the designer until locked.

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
- Artifacts SHALL be iterated-until-locked with the **designer** persona on the
  *rendered* output, exactly like every other artifact in the chain.
- WHEN an artifact is locked THEN rendered screenshots SHALL be captured as evidence
  (`design.uiArtifacts.screenshotEvidence`).

## Design

[`reference/design-artifacts.md`](../../skills/the-loop/reference/design-artifacts.md) ·
[`docs/specs/issue-18/design.md`](../specs/issue-18/design.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-18 | Made UI/UX design artifacts first-class design-phase artifacts with the designer iteration loop | [spec](../specs/issue-18/), [decision-018](../decisions/decision-018.md) |
