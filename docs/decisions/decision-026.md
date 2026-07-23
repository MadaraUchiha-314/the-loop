# Decision 026: security is a gated, per-phase concern of the spec workflow

- **Status:** accepted
- **Date:** 2026-07-23
- **Deciders:** @MadaraUchiha-314 (issue #47)
- **Work item:** issue-47
- **Spec:** `docs/specs/issue-47/`

## Context

The prompt-injection vulnerability on the trigger paths (PR #45 review →
[decision-023](decision-023.md)) was found and fixed *reactively*, at review time. The
work item's requirements and design had shipped without anyone asking the security
questions — who is untrusted, what crosses a trust boundary, what must fail closed —
because nothing in the process asked them. the-loop's premise is that quality comes
from the process; security was the one quality dimension the phase gates did not carry.

## Decision

Weave a **security lens into the existing phase gates** — requirements → design →
review — rather than adding a separate security step:

- **Requirements gate:** `requirements.md`/`bugfix.md` carry a **Security
  considerations** threat-model-lite (untrusted actors, trust boundaries, abuse cases
  as EARS criteria, fail-closed expectations). "No new attack surface" is a valid
  answer only when written and justified (`security.threatModel.required`).
- **Design gate:** `design.md` carries a **Security design** section stating how each
  requirements-phase boundary is enforced (authn/authz, input validation, injection
  surfaces, secrets, least privilege, fail-closed); an unenforced boundary fails the
  gate (`security.design.required`).
- **Implementation:** abuse cases become negative tests, named per security-relevant
  task — the existing TDD invariant, pointed at hostile inputs.
- **Ready-to-ship gate:** an explicit **security review** round after self/critic
  convergence (`security.review.required`), mechanism `auto` — the harness's built-in
  security-review skill when available, else the-loop's own checklist in
  `reference/security.md`. An unresolved security finding blocks completion at any
  tier.
- **Risk-tiered human sign-off:** effective tier ≥ `security.review.humanSignOffMinTier`
  (default 4) requires a named human to approve the security review; lower tiers run it
  autonomously, escalating only when a finding needs a security-relevant *decision*.
- **Config surface:** a top-level `security` block (`threatModel` / `design` /
  `review`) — the promotion decision-023 explicitly deferred until more security knobs
  existed. Defaults ship strict (all gates on); relaxing is an explicit, schema-visible
  edit.

## Consequences

- Templates (`requirements.md`, `bugfix.md`, `design.md`, `tasks.md`,
  `execution-log.md`), references (`workflow.md`, `reviewing.md`, new `security.md`),
  `SKILL.md`, four commands, the config schema (+ `x-onboarding` group) and both
  shipped configs change; no runtime code does.
- Every future work item pays a small, bounded cost (filling two sections, one review
  round) in exchange for security being considered up front, with a paper trail.
- **Re-evaluation triggers:** the sections rotting into boilerplate ("no new attack
  surface" rubber-stamped) — consider CLI-side spec linting; a real incident slipping
  through the checklist — revisit mechanism/checklist depth; teams wanting per-path
  security tiers rather than the single sign-off threshold.

## Alternatives considered

- **A separate security phase/step** — rejected: more ceremony, skippable, and out of
  band with the artifact chain; a lens on gates that already block is enforced for free.
- **Review-time scanning only (e.g. always run `/security-review` at the end)** —
  rejected: exactly the reactive posture that motivated this issue; by review time the
  surface is designed and built.
- **Always require a human security sign-off** — rejected: an approval firehose that
  erodes attention; risk-tiering matches the existing autonomy model (one meaningful
  signal).
- **Only the-loop's own checklist (ignore built-in skills)** — rejected: harnesses with
  a dedicated security-review skill do deeper, tool-assisted analysis; `auto` uses them
  when present and stays portable when not.
