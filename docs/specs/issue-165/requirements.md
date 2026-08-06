---
type: requirements
phase: requirements-definition
workItem: issue-165
status: approved              # draft | in-review | approved
approvedBy: []                # recorded on the PR review (paper trail)
collaborators: [product-manager, architect, engineer, reviewer]
overrides: {}
---

# Requirements: write the-loop's artifacts for a human reader

> Phase 1. Ticket: [issue #165](https://github.com/MadaraUchiha-314/the-loop/issues/165).
> Prior art and rejected options: [`brainstorm.md`](brainstorm.md).

## Introduction

A reviewer approving a work item reads `requirements.md`, `design.md`, `testing-plan.md`
and the PR briefing. Nothing sets a shape, a length or a register for them — issue-163's
requirements ran to 30 KB — and the harness's one verbosity lever
(`tokenEconomy.outputVerbosity`) compresses chat output while explicitly *preserving*
specs.

This work item adds the writing contract: a skill saying how to write for a human, budgets
saying how long, a rule preferring a diagram to a paragraph, and a carve-out keeping EARS
formal.

## Requirements

### Requirement 1 — a bundled writing skill

**User story:** As an agent authoring an artifact, I want one place defining how the-loop
writes for humans, so that every artifact reads the same way.

#### Acceptance criteria (EARS)

1. WHEN the-loop is installed THEN the system SHALL expose a bundled writing skill under
   `skills/` alongside the `the-loop` skill, discoverable by the Agent Skills standard.
2. WHEN the skill is loaded THEN it SHALL define the document spine (what changed, why,
   what it costs, what to check), the per-artifact budgets, the diagram-first rule and the
   formal carve-out.
3. WHEN the skill needs a catalogue of writing tells THEN it SHALL keep that catalogue in
   a `reference/` file so the skill body stays within its own budget.
4. WHERE prior art already solves a sub-problem THEN the system SHALL register it in
   `externalTools` rather than vendoring it (decision-005).

### Requirement 2 — budgets on the artifacts a human reads

**User story:** As a reviewer, I want each artifact short enough to read in one sitting,
so that approving a phase does not cost an hour.

#### Acceptance criteria (EARS)

1. WHEN a template for a human-read artifact is authored THEN it SHALL declare a prose
   budget in a machine-readable marker.
2. WHEN a budget is counted THEN front-matter, headings, tables, code blocks, mermaid
   blocks and EARS acceptance criteria SHALL be excluded — the budget governs prose.
3. IF an artifact exceeds its budget THEN the system SHALL cut or move content rather than
   block the phase; budgets are advisory, and the reason for any deliberate overrun is
   recorded in the artifact.
4. WHEN a gate requires a section THEN brevity SHALL NOT remove it — a section with
   nothing to say records that in one sentence.

### Requirement 3 — prefer a diagram to a paragraph

**User story:** As a reviewer, I want structure shown rather than described.

#### Acceptance criteria (EARS)

1. WHEN prose would describe a structure, sequence or state change with three or more
   named parts THEN the system SHALL author a mermaid diagram and let the prose state only
   what the diagram cannot.
2. WHEN a diagram is authored THEN it SHALL be mermaid (`userInteraction.diagramFormat`).
3. WHEN `design.md` is produced THEN it SHALL carry at least one diagram.

### Requirement 4 — formal language stays where it is a contract

**User story:** As the requirements gate, I want EARS to stay formal, so that acceptance
criteria remain testable.

#### Acceptance criteria (EARS)

1. WHEN acceptance criteria, abuse cases, API contracts, JSON-Schema descriptions or
   RFC-2119 keywords are authored THEN the writing rules SHALL NOT relax them into
   informal prose.
2. WHEN explanatory text surrounds those artifacts THEN it SHALL follow the concise
   register.

### Requirement 5 — configurable, and enforced where enforcement is mechanical

**User story:** As an operator, I want the writing contract in config like every other
the-loop policy, and a test that catches drift.

#### Acceptance criteria (EARS)

1. WHEN the harness config is validated THEN `userInteraction.writingStyle` SHALL be an
   accepted block carrying the enable flag, the budgets, the diagram-first flag and the
   formal carve-out list.
2. WHEN the test suite runs THEN it SHALL assert that the writing skill exists and parses,
   that every budgeted template declares its budget, that the schema defaults and the
   template markers agree, and that the shipped prose contains no P0 tell.
3. IF a check is a matter of judgement rather than mechanics THEN it SHALL NOT be asserted
   — presence is testable, quality is a review item.

## Non-functional requirements

- No new runtime dependency; the test is a filesystem read like `test_docs_parity`.
- The skill is itself within its own budget — the contract survives its own rule.

## Security considerations

- **Actors & trust:** none new. Skill and test read files already in the repository; no
  user input, no network, no execution.
- **Trust boundaries & data:** none crossed. The test globs repository paths and reads
  markdown.
- **Abuse cases (EARS):**
  1. WHEN the tell-catalogue is applied to text THEN the system SHALL NOT rewrite quoted
     material, code blocks, evidence output or third-party content, so that a "style fix"
     cannot silently alter a record.
  2. WHEN a budget would be met by deleting a gated section THEN the system SHALL keep the
     section and record it empty-with-reason instead.
- **Fail closed:** a malformed budget marker fails the parity test rather than being
  skipped, so a typo cannot silently disable the budget.
- **Attack surface:** `.the-loop/harness-config.yaml` and its schema are in
  `autonomy.sensitivePaths`, raising this work item to risk tier 4. The added keys are
  declarative; none becomes an argv, unlike `reviews.critics[]`.

## Out of scope

- A blocking gate on length (brainstorm Option B), and a `the-loop writing lint` command
  (Option D, deferred).
- Rewriting existing specs. They are the historical record; the contract applies forward.
- Vocabulary ban-lists.

## Open questions

1. Should budgets ever block a phase? Leaning no.
2. Do the budgets apply to `skills/the-loop/reference/*.md`? Leaning: the register does,
   the budgets do not.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
