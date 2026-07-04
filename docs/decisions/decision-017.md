# Decision 017: Add an optional brainstorm phase (the root artifact) before requirements

- **Status:** accepted
- **Date:** 2026-07-04
- **Deciders:** @MadaraUchiha-314 (issue #17)
- **Work item:** issue-17

## Context

the-loop starts a work item at `requirements.md`. But some work starts as a **fuzzy
idea** that isn't ready to be pinned down as EARS acceptance criteria yet — it needs a
scratchpad to explore the problem, weigh options, and converge before requirements make
sense. Issue #17 asked for a `brainstorm.md` and a `/brainstorm` command, and — more
importantly — framed a general principle: *feedback and iteration should happen on **every**
artifact derived from the root artifact, and the loop should only advance once the current
artifact is locked down.*

## Decision

Add **brainstorming as an optional Phase 0** whose deliverable, `brainstorm.md`, is the
**root artifact** the rest of the chain derives from:

```
brainstorm.md (optional, root) → requirements.md → design.md → tasks.md → implementation
```

Concretely:

- **New template** `.the-loop/templates/brainstorm.md` — a deliberately free-form
  scratchpad (problem, options incl. rejected ones, open questions, working hypothesis,
  hand-off). Tracked in the manifest as an **optional** work-item artifact
  (`spec-brainstorm`, phase `brainstorming`).
- **New command** `/the-loop:brainstorm <title>` — creates `brainstorm.md` in the
  pre-ticket `docs/specs/draft-<slug>/` folder and iterates it until locked.
- **Conversion** — `/the-loop:new-requirement` reads a sibling `brainstorm.md` (when
  present and locked) and **derives** requirements from it rather than starting blank;
  `/the-loop:create-ticket` promotes the brainstorm along with the rest of the folder.
- **State machine** — `brainstorming` is inserted after `not-started` in
  `workflow.phases` (schema default, both config.yaml files). It is **optional**: a
  well-defined work item transitions straight to `requirements-definition`.
- **Generalized rule** — "iterate each artifact with feedback until it is **locked**
  (`status: approved`), then derive the next and advance" is documented as a first-class
  operating principle (SKILL.md, `reference/workflow.md`, work-on), applied at every link
  of the chain, not just requirements.

## Consequences

- Fuzzy work gets a first-class home to converge before requirements, reducing churn in
  `requirements.md` from half-formed ideas.
- The loop's central idea — feedback + iteration per artifact, advance only when locked —
  is now stated once and applied uniformly, with the brainstorm as the visible root.
- Backwards compatible: brainstorming is optional and additive; existing work items and
  specs are unaffected (no `brainstorm.md` ⇒ start at requirements, exactly as before).
- One more (optional) artifact and phase label to understand; mitigated by making it
  clearly optional everywhere it appears.

## Alternatives considered

- **Fold brainstorming into `requirements.md` (a "scratch" section)** — rejected: mixes
  exploratory, throwaway thinking with the locked contract; the point is a *separate* root
  artifact whose rejected options remain the record without polluting requirements.
- **Make brainstorming mandatory** — rejected: most well-scoped work items don't need it;
  forcing it adds ceremony. Optional keeps the fast path fast.
- **A standalone `/convert-brainstorm` command** — rejected as redundant: conversion is
  exactly "produce requirements from prior context", which is what `new-requirement`
  already does; teaching it to read a sibling brainstorm avoids a second command.
