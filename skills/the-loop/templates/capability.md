<!-- Written per the `the-loop:writing` skill: front-load each section's
     conclusion, draw it rather than describe it (3+ named parts -> a mermaid
     diagram), and keep the formal registers formal (EARS, abuse cases,
     RFC-2119, API contracts, schema descriptions). No length limit — length
     follows the change; the test is whether a sentence can come out without
     losing information. A gated section stays even when it is empty. -->

# Capability: <capability name>

> One-line purpose of the capability. A **capability doc** is the organized view of the
> specs that shaped this capability: the **single source of truth for its *current*
> behaviour**. The raw specs under `<specDir>/<id>/` remain the historical record of how
> each change arrived. Update this doc **in the same PR** as any work item that changes
> the capability's behaviour (a ready-to-ship gate item), and keep the index
> (`<capabilitiesDir>/capabilities.md`) in sync.

## What it is

A short narrative: what this capability does, who uses it, and where it sits in the
product (product-feature and/or architecture shaped — both are valid).

## Current behaviour

The consolidated, **normative** statements of what the capability does today. Each
statement is traceable to a history row below. Consolidate here; do not make the reader
merge specs in ticket order.

- The system SHALL …
- WHEN <event> THEN the system SHALL …

## Design

Pointers, not copies (reference, don't duplicate): the relevant
`<specDir>/<id>/design.md` sections, `docs/architecture/` docs, and reference docs.

## History

Every work item that shaped this capability, newest first.

| Work item | What changed | Links |
|-----------|--------------|-------|
| <id> | one-line summary of the behaviour change | [spec](../specs/<id>/), [decision](../decisions/decision-<nnn>.md), PR #<n> |
