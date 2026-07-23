# Security reference — the security lens on every phase gate

Security is a **first-class, gated concern** of the spec workflow, not a bolt-on step:
each existing phase gate (requirements → design → review) also checks a security
question, and the answer is recorded in the phase's artifact. Driven by
`config.security`; born from the prompt-injection finding on the trigger paths
(decision-023 → issue-47).

The principle behind every check: **untrusted input never drives privileged behaviour,
and ambiguity fails closed.**

## Requirements phase — threat-model-lite (`security.threatModel.required`)

`requirements.md` (and `bugfix.md`) carries a **Security considerations** section — a
lightweight threat model captured alongside the acceptance criteria, while scope is
still cheap to change:

- **Actors & trust:** who interacts with the feature, and which of them are untrusted
  (anonymous users, third-party commenters, webhook payloads, fetched content…).
- **Trust boundaries & data:** where untrusted data crosses into trusted behaviour,
  and what sensitive data (secrets, tokens, PII) is stored/moved.
- **Abuse cases:** how a hostile actor would misuse the feature, as EARS criteria
  (`WHEN <hostile event> THEN the system SHALL <safe response>`) — these become
  negative tests.
- **Fail-closed expectations:** what must be rejected when identity/authorization/
  configuration is missing or ambiguous.

**"No new attack surface" is a valid answer** — but it is written down and justified
(e.g. "pure refactor, no new inputs, no new privileges"), never implied by omission.
A work item with an empty Security considerations section does not pass the
requirements gate.

If the project keeps a living threat-model doc (`security.threatModel.projectDoc`),
the section links to it and records only this work item's deltas.

## Design phase — enforce the boundaries (`security.design.required`)

`design.md` carries a **Security design** section stating **how each trust boundary
from the requirements is enforced** — mechanisms, not intentions:

- **AuthN/AuthZ:** who is identified how, and where authorization is checked (the
  authorized-actor guard of decision-023 is the house example).
- **Input validation & injection surfaces:** every untrusted ingress and its
  validation/encoding; SQL/command/path/prompt injection surfaces named explicitly.
- **Secrets handling:** where secrets come from (env/secret store, never the repo or
  logs) and where they must never appear.
- **Least privilege:** the minimum permissions/scopes/capabilities each component runs
  with.
- **Fail-closed behaviour:** the concrete response when a check cannot be made.
- **Abuse-case coverage:** each abuse case from the requirements mapped to the
  mechanism that defeats it and the test that proves it (feeds the testing strategy).

A design that leaves a requirements-phase trust boundary unenforced does not pass the
design gate.

## Implementation — abuse cases are tests

Abuse cases follow the same TDD invariant as everything else: security-relevant tasks
in `tasks.md` name the **negative test** that proves the boundary holds (unauthorized
actor rejected, malformed input refused, missing config fails closed), red→green like
any other task.

## Review phase — the security review gate (`security.review`)

Before the ready-to-ship gate can hold, a **security review** runs as its own recorded
round — complementing (not replacing) the self/critic rounds of `reviewing.md`:

- **Mechanism** (`security.review.mechanism`):
  - `auto` *(default)* — use the harness's built-in security-review skill (e.g. Claude
    Code's `/security-review`) when one is available; otherwise fall back to the
    checklist below.
  - `skill` / `checklist` — force one mechanism.
- **Findings follow the standard protocol:** reply-first-then-fix, one finding per
  commit (`reviewing.md`). A security finding is never silently dismissed — won't-fix
  requires a recorded justification, and an unresolved security finding **blocks
  completion regardless of risk tier**.
- **Record the round** in the execution log's review table with type `security`, plus
  the mechanism used and the outcome, and tick the gate item in the Security review
  section of the log.

### The checklist (fallback mechanism)

Verify against the diff, not from memory — each item pass/fail with evidence:

1. Every trust boundary in `design.md` §Security design is enforced where the design
   says it is.
2. All untrusted inputs are validated/constrained at their ingress; named injection
   surfaces (SQL/command/path/prompt) are covered.
3. Untrusted content cannot steer privileged behaviour (prompt-injection posture:
   authorized-actor guards, untrusted-data framing).
4. No secrets in code, config, logs or fixtures; secrets come from env/secret store.
5. AuthZ checks fail closed — missing identity/allowlist/config denies, never allows.
6. Components run with least privilege (scopes, file access, network).
7. Every abuse case from the requirements has a passing negative test.
8. New dependencies are justified in `design.md` and come from trusted sources.

## Human sign-off — risk-tiered (`security.review.humanSignOffMinTier`)

The autonomous checklist is enough for low-risk work; high-risk work waits for a human
(same shape as `autonomy.tiers`):

- Compute the work item's **effective risk tier** as usual (`riskTier` front-matter,
  else `autonomy.defaultTier`, raised by `autonomy.inferFromChange` on
  `autonomy.sensitivePaths`).
- **Tier ≥ `humanSignOffMinTier`** (default 4): a named human must approve the
  security review (paper trail on the PR/ticket) before the work item completes —
  autonomous completion is off the table even if `autonomy.tiers` would allow it.
- **Tier below the threshold:** the autonomous security review suffices; escalate
  anyway when a finding needs a security-relevant *decision* (accepting a residual
  risk, weakening a guard, adding an allowlist entry) — decisions belong to humans,
  detection belongs to the loop.

## Recording

Durable security decisions go to `docs/decisions/` like any other decision
(decision-023 is the template case). Learnings from findings feed the learnings
lifecycle so recurring classes of issue become checklist knowledge.
