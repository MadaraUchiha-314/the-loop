# Decision 012: Adopt eight review-driven robustness features

- **Status:** accepted
- **Date:** 2026-07-01
- **Deciders:** @MadaraUchiha-314 (PR #2 feature-proposal comment; chose "implement all")
- **Work item:** issue-1 (each feature also tracked as its own ticket)

## Context

A PR #2 comment proposed eight harness-agnostic improvements framed against the-loop's
existing artifacts. The maintainer chose to implement all eight in PR #2 and to open one
tracking issue per feature (#3–#10).

## Decision

Implement all eight now, as **config + skill surface** (no new runtime — consistent with
v0's skill-driven model; the CLI can harden them later):

| # | Issue | Feature | Realized by |
|---|-------|---------|-------------|
| 1 | #3 | Executable review method | `reference/reviewing.md`; `reviews.stopOnNoNewFindings`, `reviews.escalateOnRepeatFinding` |
| 2 | #4 | Learnings lifecycle | `config.selfImprovement`; `automation.md` §Self-improvement; `learnings/topics/` + git-ignored pending queue |
| 3 | #5 | Risk-tiered autonomy | `config.autonomy` (tiers/policy/`$defs`) + ready-to-ship gate; `workflow.md`; `riskTier` front-matter |
| 4 | #6 | TDD discipline | `config.tdd.mode`; `workflow.md` invariant; `tasks.md` template test column |
| 5 | #7 | Minimalism pass | `reference/minimalism.md`; `config.minimalism` |
| 6 | #8 | Conflict/assumption log | `docs/decisions/conflicts.md` (+ template); `collaboration.md` rule |
| 7 | #9 | Open critic harness | `reviews.critics[].harness` free-form + optional `command` |
| 8 | #10 | Idempotent init/upgrade | `commands/init`, `upgrade-the-loop`: manifest-driven, non-clobbering, `--dry-run`, drift report |

## Consequences

- The `reviews.*` config becomes a repeatable behavior, not just a declared intent; the
  learnings folder becomes a measurable lifecycle; "minimal intervention" becomes safe
  (tiered) instead of all-or-nothing; generation-time quality (TDD, minimalism) is
  recorded/advisory; unattended runs keep moving with an audit trail; the schema stops
  being a maintenance treadmill for critics; onboarding/upgrades are trust-critically
  idempotent.
- Config surface grows (`autonomy`, `tdd`, `minimalism`, `selfImprovement`, extra
  `reviews` keys) — all optional with sensible defaults and schema-validated.
- Each feature keeps its own ticket (#3–#10) so follow-up hardening (e.g. CLI enforcement)
  can run through the-loop's own 3-phase flow.

## Alternatives considered

- **Defer to separate PRs per the reviewer's sequencing** — considered; maintainer chose
  to land all eight in PR #2 (tracked in `conflicts.md`).
- **Add runtime enforcement now** — deferred; v0 is skill-driven, and the proposals are
  explicitly "implementable by the skill today, CLI-hardenable later".
