# Decision 024: Schema-driven grouped onboarding for `/init`

- **Status:** accepted
- **Date:** 2026-07-22
- **Deciders:** @MadaraUchiha-314
- **Work item:** issue-49

## Context

`.the-loop/config.yaml` has grown to ~25 top-level sections. `/the-loop:init` stamped
the template and left the user to guess what each key means, which values are legal,
and which keys actually need their input — a poor first-run experience (issue #49).
The config schema already carries per-key descriptions, defaults and enums; what was
missing was (a) an interactive onboarding that uses them, and (b) somewhere to declare
how keys club into groups and how eagerly the user must be involved.

## Decision

Encode the onboarding metadata **in the config schema itself** as a top-level
`x-onboarding` annotation: an ordered list of groups (related keys that interact,
decided together) each with a title, an explanation and an ask level
(`always` / `confirm` / `advanced`), plus `examples` on gap-prone free-form keys.
A new skill reference, `reference/onboarding.md`, defines the procedure init follows:
sensible-defaults precedence (existing answer → detected signal → schema default),
one interaction per group, enums presented with ALL possibilities, examples for
free-form keys, a `--defaults` non-interactive mode, and gap-only re-runs.
`commands/init.md` runs this as its step 2, between detection and scaffolding.

## Consequences

- The walkthrough can never drift from what the config accepts — groups, meanings,
  enums and examples all come from the one schema, and validators ignore `x-*`
  keywords so validation is untouched.
- Users decide only what genuinely needs them; everything else defaults sensibly and
  is reported, not asked.
- New config keys must be added to a group (or deliberately left advanced) when the
  schema grows — a small, self-documenting cost.

## Alternatives considered

- Hardcode the group list in `commands/init.md` — drifts from the schema; rejected.
- A separate `onboarding.yaml` — a second source of truth to keep in sync; rejected.
- Ask about every key — interaction fatigue defeats onboarding; rejected.
