# Learning 003: Cross-check every top-level section of the source, by name

- **Date:** 2026-07-01
- **Source:** system-feedback
- **Work item:** issue-1

## What happened

Even after learning-002 (translate the full detail, not just config defaults), a whole
top-level section of issue #1 — **§5 "User Interaction Principles"** (give enough context
for decisions; condensed/prioritized PR summaries that tell the reviewer where to focus;
RULE: all diagrams in mermaid; document spec→implementation insights/decisions; mandatory
user education) — had not been translated into any artifact. It survived several review
passes because the requirements (R1–R9) had silently skipped from §4 to §6.

## Learning

"Cross-check each section" only works if it is done **by enumerated section**, not by
gut feel. A distilled requirement set must be reconciled 1:1 against the numbered
sections of its source, and a missing number is a defect. Gaps hide in the seams between
sections, exactly where a human skim won't catch them.

## Action

- Added **R10 (user-interaction principles)**, `config.userInteraction` (schema + both
  configs), a "User-interaction principles" section in `reference/collaboration.md`, a
  SKILL rule, and enriched `work-on` Complete step; mapped R10 in `design.md`/`tasks.md`.
- Going forward, when distilling a source into requirements, keep the requirement→source
  mapping explicit and verify **every** source section number appears (delivered or an
  explicitly recorded deferral) before calling the distillation complete.
