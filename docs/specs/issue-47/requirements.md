---
type: requirements
phase: requirements-definition
workItem: issue-47
status: draft
approvedBy: []
collaborators: [product-manager, architect, engineer]
overrides: {}
---

# Requirements: security as a first-class, gated concern in the work-item process

> Phase 1 of 3 (requirements → design → tasks). Ticket:
> [issue #47](https://github.com/MadaraUchiha-314/the-loop/issues/47). This phase should
> be reviewed and approved before moving to design.

## Introduction

The prompt-injection finding on the trigger paths (PR #45 review →
[decision-023](../../decisions/decision-023.md)) showed that security was being patched
reactively, at review time, after the surface had already shipped in a spec nobody had
looked at through a security lens. the-loop's own thesis is that quality is produced by
the *process* — so security must be woven into the existing phase gates (requirements →
design → review), considered by default on every work item, not bolted on as an
occasional extra step.

This work item makes security a **gated concern of each phase**: a threat-model-lite in
the requirements, an enforcement statement in the design, an explicit security review in
the ready-to-ship gate, and a risk-tiered human sign-off — all driven by a new
`security` config block.

## Requirements

### Requirement 1 — requirements phase captures a threat-model-lite

**User story:** As a work-item owner, I want abuse cases and trust boundaries captured
alongside the acceptance criteria, so that security is scoped while it is still cheap to
change.

#### Acceptance criteria (EARS)

1. WHEN a `requirements.md` (or `bugfix.md`) is drafted THEN the artifact SHALL carry a
   **Security considerations** section covering untrusted actors, trust boundaries and
   data crossing them, abuse cases (as EARS criteria), and fail-closed expectations.
2. IF a work item genuinely adds no attack surface THEN the section SHALL say so with a
   written justification — omission or an empty section SHALL fail the requirements
   gate (`security.threatModel.required`, default true).
3. WHERE a project-level living threat-model doc is configured
   (`security.threatModel.projectDoc`) the section SHALL link it and record only this
   work item's deltas.

### Requirement 2 — design phase enforces the boundaries

**User story:** As a reviewer, I want the design to state *how* each trust boundary is
enforced, so that enforcement is a designed mechanism, not an implementation accident.

#### Acceptance criteria (EARS)

1. WHEN a `design.md` is derived from approved requirements THEN it SHALL carry a
   **Security design** section stating how each requirements-phase trust boundary is
   enforced: authn/authz, input validation and injection surfaces (SQL/command/path/
   prompt), secrets handling, least privilege, and fail-closed behaviour.
2. IF a trust boundary from the requirements is left unenforced by the design THEN the
   design SHALL NOT pass its phase gate (`security.design.required`, default true).
3. The section SHALL map each abuse case to the mechanism defeating it and the negative
   test proving it, feeding the testing strategy.

### Requirement 3 — abuse cases become tests

**User story:** As an operator trusting the loop's autonomy, I want security claims
proven by tests, so that "the boundary holds" is evidence, not assertion.

#### Acceptance criteria (EARS)

1. WHEN `tasks.md` includes a security-relevant task (it touches a trust boundary from
   the Security design) THEN the task SHALL name the negative test proving the boundary
   holds, red→green like any other task (`tdd.mode` invariant unchanged).

### Requirement 4 — an explicit security review gates completion

**User story:** As an operator, I want a security review to be a condition of shipping,
so that no work item completes — autonomously or not — without a security pass.

#### Acceptance criteria (EARS)

1. WHEN the self/critic review rounds converge THEN the loop SHALL run a **security
   review** as its own recorded round, and the ready-to-ship gate SHALL include its
   passing (`security.review.required`, default true).
2. The mechanism SHALL be configurable (`security.review.mechanism`): `auto` (default —
   the harness's built-in security-review skill when available, else the-loop's own
   checklist), `skill`, or `checklist`; the fallback checklist SHALL ship in the
   operating skill's security reference.
3. WHEN the security review produces findings THEN they SHALL follow the standard
   reply-first-then-fix protocol, AND an unresolved security finding SHALL block
   completion regardless of risk tier.
4. The round SHALL be recorded in the execution log (review table type `security` plus
   a dedicated Security review gate section: mechanism, outcome, sign-off).

### Requirement 5 — human sign-off is risk-tiered

**User story:** As an owner, I want high-risk work to wait for a human security
sign-off while low-risk work stays autonomous, so that the gate adds safety without a
firehose of approvals.

#### Acceptance criteria (EARS)

1. WHEN a work item's effective risk tier (existing `autonomy` computation) is ≥
   `security.review.humanSignOffMinTier` (default 4) THEN a named human SHALL approve
   the security review (paper trail) before completion, even where `autonomy.tiers`
   would allow autonomous completion.
2. WHILE the tier is below the threshold the autonomous security review SHALL suffice,
   AND the loop SHALL still escalate when a finding requires a security-relevant
   *decision* (accepting residual risk, weakening a guard, extending an allowlist).

### Requirement 6 — one config surface, validated

**User story:** As a project configuring the-loop, I want the security gates driven by
one schema-validated `security` block, so that the posture is explicit and portable.

#### Acceptance criteria (EARS)

1. The system SHALL add a top-level `security` block (`threatModel`, `design`,
   `review`) to `config.schema.json`, both shipped `config.yaml`s, and the `/init`
   onboarding groups (promoting the block deferred in decision-023).
2. WHEN `scripts/validate_config.py` runs THEN both configs SHALL validate against the
   extended schema.

## Non-functional requirements

- The gates reuse existing machinery (phase gates, review protocol, autonomy tiers,
  execution log) — no new phase, command, or runtime code.
- Templates and references stay terse; the detail lives in one new
  `reference/security.md`, referenced everywhere else.

## Security considerations

> This work item's own threat-model-lite (dogfooding the section it introduces).

- **Actors & trust:** the change is process/docs/config only; no new runtime input or
  actor is introduced.
- **Trust boundaries & data:** none added; the work *documents* how future boundaries
  must be captured and enforced.
- **Abuse cases:** a mis-set `security.review.humanSignOffMinTier: 6` disables the
  human sign-off — mitigated by the schema documenting the semantics and the default
  (4) requiring humans for high tiers; `review.required: false` is an explicit,
  reviewable config choice, visible in the config diff.
- **Fail closed:** defaults are the strict posture (all three gates required); relaxing
  any of them requires an explicit config edit.

## Out of scope

- Automated *enforcement* of the gates by the CLI (linting specs for the sections,
  blocking merges) — the gates are operating-model rules executed by the harness, like
  the other phase gates; CLI enforcement can be a follow-up.
- Runtime security features (the authorized-actor guard landed in decision-023).
- A required project-wide threat-model document — `security.threatModel.projectDoc`
  supports one, empty by default.

## Open questions

Raised on the ticket; the defaults above (mechanism `auto`, sign-off tier 4) resolve the
issue's open questions pending review.
