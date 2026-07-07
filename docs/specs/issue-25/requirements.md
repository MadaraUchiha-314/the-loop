---
type: requirements
phase: requirements-definition
workItem: issue-25
status: approved
approvedBy: ["@MadaraUchiha-314 (PR #26 review: implement in this PR itself)"]
collaborators: [product-manager, architect]
overrides: {}
---

# Requirements: specs organization and capability documentation

> **Source of truth:** GitHub [issue #25](https://github.com/MadaraUchiha-314/the-loop/issues/25).
> Derived from the locked [`brainstorm.md`](brainstorm.md), whose open questions were all
> answered by the reviewer in PR #26. Design and the task DAG live in `design.md` and
> `tasks.md`.

## Introduction

Specs are produced work item by work item under `docs/specs/<id>/` — the right shape
for *making* a change, the wrong shape for *reading* the product: the current behaviour
of any capability is smeared across every spec that ever touched it. This work item
adds the **organized view**: living **capability documentation** under
`docs/capabilities/`, one doc per capability, maintained by the loop itself. Per the
locked brainstorm: raw specs are *deltas* (history), capability docs are *state*
(current truth) — and the organized spec **is** the capability documentation, not a
third artifact kind.

## Requirements

### R1 — Two-layer split: raw specs unchanged, organized layer added

**User story:** As a maintainer, I want per-work-item specs to remain exactly where and
what they are, with a separate organized layer, so that the paper trail and loop
resumability are untouched.

#### Acceptance criteria (EARS)

1. WHEN a work item's spec artifacts are created THEN the system SHALL continue to
   store them under `<workflow.specDir>/<id>/` with no change in structure or naming.
2. WHEN the organized layer is introduced THEN the system SHALL NOT move, rename or
   rewrite any existing file under `docs/specs/`.

### R2 — Capability docs are the single source of truth for current behaviour

**User story:** As a reader (human or AI), I want one living document per capability
stating its current behaviour, so that I do not have to merge N specs in ticket order.

#### Acceptance criteria (EARS)

1. WHEN a capability exists in the product THEN the system SHALL document it in a
   single file `<workflow.capabilitiesDir>/<capability>.md` (default
   `docs/capabilities/`).
2. WHILE a capability doc and raw specs both describe a behaviour, the capability doc
   SHALL be the normative statement of *current* behaviour and the raw specs SHALL be
   the historical record of how it arrived.
3. WHEN a capability doc is written THEN it SHALL contain: what the capability is
   (narrative), current behaviour (consolidated requirements), design pointers, and a
   history table.

### R3 — Traceability

**User story:** As a reviewer, I want every capability doc to link the work items and
decisions that shaped it, so that "why is it like this?" is one hop away.

#### Acceptance criteria (EARS)

1. WHEN a work item changes a capability THEN the capability doc's history table SHALL
   gain a row linking `docs/specs/<id>/` (and any decision record) with a one-line
   summary of what changed.

### R4 — Taxonomy: both shapes, evolved through PR review

**User story:** As a user of the-loop, I want the capability taxonomy to reflect both
product features and architecture, and to be correctable in review, so that the
organization matches how the product is actually read.

#### Acceptance criteria (EARS)

1. WHEN capability docs are minted THEN the taxonomy SHALL admit both product-feature
   shaped and architecture shaped capabilities.
2. WHEN a work item first touches an undocumented capability THEN the loop SHALL mint
   the capability doc in that work item's PR (emergent taxonomy, no up-front curation).
3. WHEN a reviewer gives feedback on the structure or organization of capability docs
   in PR review THEN the system SHALL treat it like any other review feedback
   (reply-first-then-fix, ordinary diffs).
4. WHEN a capability doc is added or renamed THEN the index
   `<workflow.capabilitiesDir>/capabilities.md` SHALL be updated in the same PR.

### R5 — Fold-in happens in the same PR, gated at ready-to-ship

**User story:** As a maintainer, I want the capability docs updated in the same PR as
the work item that changes behaviour, so that the organized view cannot silently rot.

#### Acceptance criteria (EARS)

1. WHEN a work item changes the behaviour of one or more capabilities THEN the loop
   SHALL update the affected capability doc(s) in the same PR as the implementation.
2. WHEN the ready-to-ship gate is evaluated THEN it SHALL include "affected capability
   docs updated (or none affected)" as a required item, alongside the existing items.
3. IF a work item affects no capability's behaviour (e.g. a pure refactor or CI fix)
   THEN the gate item SHALL pass with "none affected" recorded in the execution log.

### R6 — Template, config and manifest wiring

**User story:** As a project using the-loop, I want the capability-doc convention
scaffolded and configurable, so that any repo adopting the loop gets the same layer.

#### Acceptance criteria (EARS)

1. WHEN the-loop is installed THEN `.the-loop/templates/capability.md` SHALL exist and
   define the capability-doc structure (R2.3).
2. WHEN configuration is validated THEN `workflow.capabilitiesDir` SHALL be a valid key
   (default `docs/capabilities`) in `config.schema.json`, set in this repo's
   `config.yaml` and in `templates/config.yaml`.
3. WHEN `.the-loop/manifest.yaml` is read THEN it SHALL track the capability template
   and the capability-docs knowledge files.
4. WHEN the skill and workflow reference are read THEN they SHALL state the fold-in
   rule, the gate item, and the raw-vs-organized split.

### R7 — Backfill from existing specs

**User story:** As a reader, I want the existing product documented by capability from
day one, so that the organized layer is immediately useful rather than aspirational.

#### Acceptance criteria (EARS)

1. WHEN this work item completes THEN capability docs SHALL exist covering the
   behaviour delivered by the existing specs (issue-1, issue-11, issue-12, issue-15,
   issue-17, issue-18, issue-21) and by this work item (issue-25), each with history
   rows linking back to those specs.

## Non-functional requirements

- All new/changed markdown passes the repo's markdownlint gate; config changes pass
  schema validation (`scripts/validate_config.py`) — same commands as CI.
- Minimalism: capability docs consolidate requirements but **link** to design/specs for
  detail (reference, don't duplicate anything except the normative current-behaviour
  statements that move here by design).

## Out of scope

- Automated extraction/generation tooling (e.g. a CLI command that builds capability
  docs from specs) — the loop maintains them as authored artifacts for now.
- Moving, renaming or rewriting existing `docs/specs/<id>/` content (rejected Option B).
- Retrofitting `docs/architecture/` — it remains the "how it's built" view; overlaps
  are handled by linking.

## Open questions

None — all five brainstorm questions were answered in PR #26 review (see
[`brainstorm.md`](brainstorm.md) § Open questions (resolved)).
