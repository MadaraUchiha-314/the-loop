# Learning 002: Translate the full detail into the artifacts, not just config defaults

- **Date:** 2026-06-30
- **Source:** user-feedback
- **Work item:** issue-1

## What happened
The first cut encoded much of issue #1's detail only as config defaults and terse
command/skill summaries. The PR review flagged that "a lot of the details... haven't
been properly translated to the artifacts" and that the essence risked being lost.

## Learning
Config defaults are not enough. The behavioural detail (rules, tooling matrix, paper-
trail, observability, persona→task mapping, open questions) must live in the
plugin-facing artifacts the harness actually reads at runtime — the skill and its
reference files — or it will not be applied. Concise is good; lossy is not.

## Action
- Added `skills/the-loop/reference/` files carrying the full detail and made SKILL.md an
  index over them; enriched the commands to point at and use them.
- Going forward, when distilling a source (issue/spec) into artifacts, cross-check each
  section of the source against a concrete artifact and record any deliberate deferral —
  don't let detail fall through to "defaults only".
