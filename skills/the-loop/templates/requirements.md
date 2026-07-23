---
type: requirements
phase: requirements-definition
workItem: ""                 # ticket id this spec delivers
status: draft                # draft | in-review | approved
approvedBy: []               # handles/roles who approved this phase (paper trail)
collaborators: []            # roles required up-front, e.g. [product-manager, architect]
overrides: {}                # per-task overrides of .the-loop/config.yaml
---

# Requirements: <work item title>

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

A short summary of the feature/work item and the problem it solves. Link the ticket.

## Requirements

### Requirement 1 — <short name>

**User story:** As a <persona>, I want <capability>, so that <benefit>.

#### Acceptance criteria (EARS)

1. WHEN <event/condition> THEN the system SHALL <observable response>.
2. IF <precondition> THEN the system SHALL <observable response>.
3. WHILE <state> the system SHALL <observable response>.

### Requirement 2 — <short name>

**User story:** As a <persona>, I want <capability>, so that <benefit>.

#### Acceptance criteria (EARS)

1. WHEN <event/condition> THEN the system SHALL <observable response>.

## Non-functional requirements

Performance, observability, accessibility, etc. (as applicable). Security has its own
gated section below.

## Security considerations

> Threat-model-lite, captured with the requirements (`security.threatModel.required`,
> default true). "No new attack surface" is a valid answer — written down and
> justified, never implied by omission. See `reference/security.md`.

- **Actors & trust:** who interacts with this feature; which actors/inputs are
  **untrusted** (anonymous users, third-party comments, webhook payloads, fetched
  content…).
- **Trust boundaries & data:** where untrusted data crosses into trusted behaviour;
  what sensitive data (secrets, tokens, PII) is stored or moved.
- **Abuse cases (EARS):** how a hostile actor would misuse this — these become
  negative tests.
  1. WHEN <hostile event/input> THEN the system SHALL <safe response>.
- **Fail closed:** what MUST be rejected when identity/authorization/configuration is
  missing or ambiguous.

## Out of scope

What this work item explicitly does not cover.

## Open questions

Questions for collaborators are raised as ticket comments (paper trail) and linked here.
