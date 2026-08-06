---
type: bugfix
phase: requirements-definition
workItem: ""
status: draft                # draft | in-review | approved
approvedBy: []
severity: medium             # low | medium | high | critical
collaborators: [engineer]    # a simple bug usually needs only the engineer
overrides: {}
---

<!-- Written per the `the-loop:writing` skill: front-load each section's
     conclusion, draw it rather than describe it (3+ named parts -> a mermaid
     diagram), and keep the formal registers formal (EARS, abuse cases,
     RFC-2119, API contracts, schema descriptions). No length limit — length
     follows the change; the test is whether a sentence can come out without
     losing information. A gated section stays even when it is empty. -->

# Bugfix spec: <work item title>

> Phase 1 of 3 for a bug (bugfix → design → tasks). For simple bugs the design phase
> may be minimal. This phase MUST be reviewed/approved before moving on.

## Summary

What is wrong, and the observed impact. Link the ticket.

## Steps to reproduce

1.
2.
3.

## Expected vs actual

- **Expected:** what should happen.
- **Actual:** what happens instead. Include logs/errors (same format as runtime).

## Root cause (hypothesis / confirmed)

What is causing the bug, once known.

## Requirements

> This exact heading is what the `requirements-definition` gate looks for — the same one
> `requirements.md` uses, because a bug and a feature clear the same gate. For a bug the
> requirements are usually one or two: restore the correct behaviour, and prove it stays
> restored.

### Requirement 1 — <the correct behaviour>

#### Acceptance criteria (EARS)

1. WHEN <repro steps> THEN the system SHALL <correct behaviour>.
2. The fix SHALL include a regression test that fails before the fix and passes after.

## Security considerations

> Same gate as requirements (`security.threatModel.required`); usually short for a bug.
> See `reference/security.md`.

- Is the bug itself security-relevant (exploitable, data-exposing)? If so, treat its
  abuse case as an acceptance criterion above.
- Does the fix touch a trust boundary (auth, validation, secrets, untrusted input)?
  State how the boundary still fails closed — or record "no new attack surface" with
  the justification.

## Out of scope

Related issues intentionally not addressed here.

## Open questions

Raised as ticket comments and linked here.
