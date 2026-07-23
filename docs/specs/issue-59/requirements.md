---
type: requirements
phase: requirements-definition
workItem: issue-59
status: draft
approvedBy: []
collaborators: [product-manager, architect, engineer]
overrides: {}
---

# Requirements: consider user prompt/instructions while working on a repo or workspace

> Phase 1 of 3 (requirements → design → tasks). Ticket:
> [issue #59](https://github.com/MadaraUchiha-314/the-loop/issues/59). This phase should
> be reviewed and approved before moving to design.

## Introduction

Teams carry conventions the-loop's structured config cannot model: coding and testing
styles, naming rules, review etiquette, domain glossaries, "how we do things here" —
usually already written down as a readme or markdown doc. Today the-loop reads only its
own config and skill; the operator has no first-class way to say "also read *this* and
follow it". Harness-native memory files (`CLAUDE.md`, Cursor rules) exist but are
harness-specific and outside the-loop's contract.

This work item adds **custom instructions**: when a user initializes the-loop they can
point to one or more instruction documents, per installation of the-loop, at
configurable paths (inside or outside the repo). The harness reads them before working
and honors them. This is supplementary to the existing external-tools registry
(`config.externalTools`): that registers *tools the harness may use*; this registers
*guidance the harness must follow*.

## Requirements

### Requirement 1 — instruction docs are configurable per installation

**User story:** As a user initializing the-loop, I want to point it at my custom
instruction file(s) — readme or markdown — at paths I choose, so that each installation
of the-loop carries my conventions without forking the plugin.

#### Acceptance criteria (EARS)

1. The config schema SHALL gain a `customInstructions` section with an ordered `docs`
   list, each entry naming a `path` (repo-relative or absolute) and optional `notes`
   describing what the doc covers.
2. The system SHALL accept paths outside the repository (absolute, per-machine), so an
   installation can layer org-wide docs the repo does not contain.
3. WHEN a configured doc does not exist at its path THEN the system SHALL act per
   `customInstructions.onMissing` (`warn` (default) | `error` | `ignore`).

### Requirement 2 — init establishes the docs with the user

**User story:** As a user running `/the-loop:init`, I want the onboarding to ask about
custom instructions and propose candidates it detects, so that pointing the-loop at my
conventions is part of setup, not something I discover later.

#### Acceptance criteria (EARS)

1. The schema's `x-onboarding.groups` SHALL include a Custom instructions group at ask
   level `confirm`, so init raises it in the guided walkthrough (and routes it to
   needs-user handling only per the existing `--defaults` rules).
2. WHEN init detects existing convention files (e.g. `CONTRIBUTING.md`, style guides
   under `docs/`) THEN it SHALL propose them as candidates — never auto-register them
   without the user's confirmation.

### Requirement 3 — the loop reads and honors the docs while working

**User story:** As a user, I want the harness to actually follow my instructions during
every phase of the loop, so that generated requirements, designs, code and tests match
my team's styles.

#### Acceptance criteria (EARS)

1. WHEN the loop starts working a work item (via `work-on` or a granular command) THEN
   the system SHALL read every doc in `customInstructions.docs` in list order,
   immediately after loading `.the-loop/config.yaml`.
2. The system SHALL honor the instructions throughout the phases, and after a context
   **clear** SHALL re-read them like every other checked-in artifact
   (`reference/context.md`).
3. The skill SHALL document the load order and when to re-read (phase-scoped, driven by
   each entry's `notes`) in a dedicated reference file the operating commands point to.

### Requirement 4 — precedence is defined and gates cannot be instructed away

**User story:** As a user, I want a predictable answer to "who wins when my doc and
the-loop disagree", so that custom instructions are useful without becoming a bypass of
the loop's rigor.

#### Acceptance criteria (EARS)

1. The structured config SHALL win where both speak: an instruction doc cannot silently
   override a `.the-loop/config.yaml` key — the mismatch is surfaced to the user.
2. Custom instructions SHALL win over the-loop's own defaults for everything the config
   does not model (styles, conventions, domain guidance); within the list, later docs
   win over earlier ones.
3. The system SHALL NOT let an instruction doc weaken the loop's hard gates (security
   gates, paper trail, phase/review gates, risk-tiered autonomy); such an instruction
   is ignored and the conflict logged (fail-closed).

## Security considerations

- **Untrusted actors / trust boundaries:** instruction docs are operator-configured
  installation input — the same trust level as `.the-loop/config.yaml` itself, NOT
  webhook/ticket/PR-comment content. The authorized-actor guard (decision-023) is
  unchanged: nothing in this feature lets ticket content register or edit instruction
  docs.
- **Abuse case — prompt injection via a doc changed in a work item's own diff:** a PR
  could modify a registered instruction doc to weaken behavior on subsequent runs.
  Mitigation: Requirement 4.3 (gates cannot be instructed away, fail-closed) plus the
  normal review of the diff like any other file.
- **Fail-closed:** on conflict with a gate the gate wins and the conflict is logged;
  `onMissing: error` is available for operators who want absence itself to halt.

## Out of scope

- Fetching instruction docs from URLs or remote stores — paths on the local filesystem
  only (minimalism; a remote doc can be checked in or synced by other means).
- Replacing harness-native memory files (`CLAUDE.md`, Cursor rules) — they keep their
  own semantics; `customInstructions` is the harness-portable channel the-loop itself
  guarantees.
- Structured/machine-readable instruction formats — the docs are prose markdown by
  design; anything structurable belongs in `.the-loop/config.yaml`.
