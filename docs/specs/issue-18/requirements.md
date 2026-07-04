---
type: requirements
phase: requirements-definition
workItem: issue-18
status: approved
approvedBy: ["@MadaraUchiha-314 (issue #18 as authored)"]
collaborators: [product-manager, designer, architect]
overrides: {}
---

# Requirements: UI/UX design artifacts in the design phase

> **Source of truth:** GitHub [issue #18](https://github.com/MadaraUchiha-314/the-loop/issues/18).
> Design and the task DAG live in `design.md` and `tasks.md`.

## Introduction

`design.md` (markdown + mermaid) captures architecture/HLD/LLD well, but it is the wrong
medium for **UI/UX** design, which is visual. Modern UI/UX design is represented as **Figma
files** and, increasingly, as **HTML + CSS + JS** prototypes (how Claude's design artifacts
express a rendered, clickable design). Make these **valid, first-class artifacts tracked by
the-loop** in the design phase, and **define the patterns** by which designers iterate on
the generated design artifacts.

## Requirements

### R1 — UI/UX design artifacts are first-class design-phase artifacts

**User story:** As a designer, I want the visual design tracked as first-class artifacts
alongside `design.md`, so that UI/UX intent is versioned, reviewed and locked like every
other artifact.

#### Acceptance criteria (EARS)

1. WHEN a work item has a user-facing surface THEN the design phase SHALL support tracked
   UI/UX design artifacts — **Figma links** and/or **self-contained HTML+CSS+JS
   prototypes** — as siblings of `design.md`.
2. Checked-in artifacts SHALL live under `docs/specs/<id>/design/` (`design.uiArtifacts.dir`),
   and SHALL be listed in `.the-loop/manifest.yaml` as an **optional**
   `spec-design-artifacts` work-item artifact (phase `design`).
3. `design.md` SHALL carry a **UI/UX design** section inventorying each artifact (type,
   location/link, screen·requirement covered, lock status).

### R2 — configuration for UI/UX artifacts

**User story:** As a maintainer, I want the UI/UX artifact conventions configurable, so
that a project can pick its representation and location.

#### Acceptance criteria (EARS)

1. The schema SHALL provide a `design.uiArtifacts` section with `dir` (default `design`),
   `format` (`html`|`figma`|`both`, default `html`), `selfContained` (default true) and
   `screenshotEvidence` (default true); both shipped `config.yaml` files SHALL include it;
   `config.yaml` SHALL keep validating against `config.schema.json`.

### R3 — self-contained HTML prototypes

**User story:** As a reviewer, I want HTML prototypes to render standalone, so that I can
open them in a browser or as a Claude-style artifact without a build or network.

#### Acceptance criteria (EARS)

1. WHEN `design.uiArtifacts.format` is `html` and `selfContained` is true THEN a prototype
   SHALL inline all CSS/JS and embed assets as `data:` URIs with **no external network
   dependencies**.

### R4 — the designer iteration pattern is defined

**User story:** As a designer, I want a defined pattern for iterating on generated design
artifacts, so that visual design converges predictably and leaves a paper trail.

#### Acceptance criteria (EARS)

1. A reference (`reference/design-artifacts.md`) SHALL define the loop: generate/curate →
   render → **designer** reviews the *rendered* output → feedback as **ticket comments** →
   iterate (edit the checked-in artifact, not new copies) → **lock** (`status: approved`)
   → screenshots as evidence and hand-off to implementation.
2. It SHALL state that the loop reuses the existing iterate-until-locked rule, per-phase
   human review, the `designer` persona and the paper-trail rule; and that the locked
   artifact is the **visual contract** implementation matches.

### R5 — wired into commands and docs

**User story:** As a user running the loop, I want the design commands and skill to know
about UI/UX artifacts, so that they are produced and reviewed as part of the design phase.

#### Acceptance criteria (EARS)

1. `create-design` and `work-on` SHALL instruct producing and iterating UI/UX artifacts
   when the work item is user-facing (and skipping with `N/A` otherwise).
2. `SKILL.md`, `reference/workflow.md`, `reference/collaboration.md`, the design template
   and `README.md` SHALL document the UI/UX design artifact convention and reference
   `reference/design-artifacts.md`.

## Non-functional requirements

- **Backwards compatible & additive.** Work items with no user-facing surface produce no
  `design/` folder and an `N/A` UI/UX section; existing specs are unaffected.
- **Docs lint clean.** All new/changed markdown passes `markdownlint`.
- **Config valid.** `config.yaml` continues to validate against `config.schema.json`.

## Out of scope

- Automating the *quality* of generated UI (it remains an agent/designer task).
- Visual-regression tooling integration (named as a hand-off direction, not built here).
- CLI (`the_loop`) code changes — this work item is plugin docs/templates/config.

## Open questions

None.
