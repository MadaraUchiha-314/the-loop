---
type: requirements
phase: requirements-definition
workItem: issue-1
status: approved
approvedBy: ["@MadaraUchiha-314 (issue author intent)"]
collaborators: [product-manager, architect, engineer]
overrides: {}
---

# Requirements: The Loop — bootstrap the-loop (create itself)

> the-loop uses the-loop. This is the retroactively-captured spec for the v0 bootstrap
> requested by [issue #1](https://github.com/MadaraUchiha-314/the-loop/issues/1).

## Introduction
the-loop is an opinionated PDLC harness shipped as a Claude plugin. The first work item
is for the-loop to create itself: establish the distributable plugin and the project
contracts/structure that encode the workflow described in issue #1.

## Requirements

### Requirement 1 — Installable plugin distribution
**User story:** As a user, I want to install the-loop into my harness from GitHub, so
that I can use its commands and skill.
#### Acceptance criteria (EARS)
1. WHEN the repo is added as a marketplace THEN it SHALL expose a valid
   `.claude-plugin/marketplace.json` and `.claude-plugin/plugin.json`.
2. WHEN installed THEN the `init`, `work-on` and `upgrade-the-loop` commands and the
   `the-loop` skill SHALL be available.

### Requirement 2 — Versioned configuration contract
**User story:** As the harness, I want a validated config, so that behaviour is
predictable and upgradeable.
#### Acceptance criteria (EARS)
1. WHEN a project is initialized THEN a `.the-loop/config.yaml` SHALL exist and SHALL
   validate against `.the-loop/config.schema.json`.
2. The config SHALL support per-work-item overrides via markdown front-matter.

### Requirement 3 — 3-phase spec workflow & phase tracking
**User story:** As a collaborator, I want work specified in reviewable phases, so that I
approve requirements, design and tasks before implementation.
#### Acceptance criteria (EARS)
1. WHEN a work item is worked on THEN the-loop SHALL produce `requirements`/`bugfix`,
   `design` and `tasks` specs under `docs/specs/<id>/`.
2. The system SHALL track the work item phase via ticket labels across
   `not-started → … → complete` and require a human review at the end of each spec phase.

### Requirement 4 — Knowledge & self-improvement structure
**User story:** As a user, I want decisions and learnings checked in, so that I can
review and the system can improve.
#### Acceptance criteria (EARS)
1. The repo SHALL contain `docs/architecture/`, `docs/decisions/` and `learnings/` with
   indexes and numbered records.
2. Every managed file SHALL be tracked in `.the-loop/manifest.yaml`.

## Non-functional requirements
- All JSON SHALL parse; configs SHALL validate against the schema.
- No bespoke marketplace; installable directly from GitHub.

## Out of scope (deferred — see decision-003)
Runtime automation: webhook triggers, remote-workspace execution, DAG orchestration,
concrete per-language tooling integrations, messaging integrations, Cursor packaging.

## Open questions
- Cursor distribution equivalent — TODO, tracked as future work.
