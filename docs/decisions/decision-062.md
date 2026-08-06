# Decision 062: Third-party writing skills are registered, not vendored — and their ban-lists are not adopted

- **Status:** proposed
- **Date:** 2026-08-06
- **Deciders:** @MadaraUchiha-314 (issue #165)
- **Work item:** issue-165
- **Spec:** `docs/specs/issue-165/` (survey in
  [`brainstorm.md`](../specs/issue-165/brainstorm.md))
- **Follows:** the register-only posture already applied to `caveman` and `ponytail`
  (issue-37), and [decision-005](decision-005.md)'s stdlib-first, bundle-no-runtime stance.

## Context

[Issue #165](https://github.com/MadaraUchiha-314/the-loop/issues/165) asked for a
literature survey before building anything. Surveyed August 2026: `avoid-ai-writing`
(MIT), `anti-ai-slop-writing` (MIT), Stop Slop, several technical-writing-expert skills,
the plain-language style-guide tradition (Google / Microsoft / GOV.UK), and
[Diátaxis](https://diataxis.fr).

The finding that shaped the design: **every existing skill treats this as a vocabulary
problem.** Ban "delve", "leverage", "robust"; rewrite the sentence. That is the wrong
altitude for the-loop. A 30 KB requirements document does not get better by losing the
word "leverage" — it gets better by being 3 KB.

## Decision

**Register the prior art; adopt its structure and its warning; leave its ban-lists.**

- `avoid-ai-writing`, `anti-ai-slop-writing` and `stop-slop` are entries in
  `externalTools.tools` with notes recording exactly what was and was not taken. An
  operator who prefers the packaged version installs it; the-loop bundles no copy.
- **Taken:** severity tiering (P0/P1/P2) and detect-before-rewrite from `avoid-ai-writing`;
  the short-contract-plus-long-catalogue file shape from `anti-ai-slop-writing`;
  throat-clearing openers as the highest-yield cut from Stop Slop; front-load-the-conclusion
  and one-idea-per-paragraph from the style guides; from Diátaxis, the *diagnosis* that
  documents bloat when they mix explanation with reference — which is why the-loop's answer
  is a per-artifact shape rather than a per-sentence rule.
- **Not taken:** the word-tier ban-lists, the blanket em-dash ban, and the four-mode
  taxonomy. "Leverage" and "robust" are ordinary technical English; a build that goes red
  over them is a build people route around. the-loop's artifacts already have names and
  gates, so they do not need Diátaxis's.
- **Taken as a constraint:** `avoid-ai-writing`'s own warning that these patterns are
  signals, not proof, with false-positive rates above 60% on non-native speakers. It is the
  reason `test_writing_parity.py`'s P4 asserts only tells with no legitimate technical
  reading, and why the rest of the catalogue stays in `skills/writing/reference/tells.md`
  as judgement.

## Consequences

- One place to look when a writing rule is questioned: the skill, with the survey behind
  it in the work item's brainstorm.
- The registry entries carry the reasoning, so a future contributor proposing "let's just
  install the popular one" finds the answer already written down.
- If the tells catalogue drifts from the upstream skills, nothing breaks — it was never a
  fork.
