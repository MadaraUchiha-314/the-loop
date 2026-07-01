# Learning 007: A mandatory behavior needs a trigger point, not just a rule

- **Date:** 2026-07-01
- **Source:** user-feedback
- **Work item:** issue-1

## What happened

R10 declares reviewer education **mandatory** (condensed, prioritized, mermaid-illustrated
PR briefing). Yet across all of PR #2 it never happened — the reviewer got a stream of
per-change replies and asked, in a retro, "why wasn't the education part triggered?" The
rule was written into the skill, config, and requirements, but **no step in the workflow
forced it to fire** before review was requested.

## Learning

Declaring a behavior "mandatory, not optional" in prose does not make it happen. A
mandatory behavior needs an explicit **trigger point** wired into the workflow — a gate
that cannot be passed without it — otherwise the agent defaults to whatever is locally
convenient (here: incremental replies) and the rule silently no-ops. "Where does this
fire, and what blocks progress if it didn't?" must be answered for every mandatory rule.

## Action

- Made the reviewer briefing a **required item of the ready-to-ship gate**, produced from
  `.the-loop/templates/pr-briefing.md`, posted before human review (`decision-013`).
- Going forward, every rule marked mandatory must name its trigger point and its gate; a
  mandatory rule with no enforcing step is treated as incomplete.
