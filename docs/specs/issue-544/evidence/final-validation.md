---
type: evidence
workItem: issue-544
---

# Final validation: make what the-loop writes easy to read and review

> The `evidence` node's proof, summarised from `testing-plan.md`'s Verification results
> and [`verification.md`](verification.md), and mapped onto the acceptance criteria.
> Raw captures sit beside this file under `evidence/`.

Every acceptance criterion is met. Every planned activity ran and passed on 2026-11-18. The full suite (`make check`, clean environment) passed with 7,043 tests, and the three review rounds (self, critic, security) left no open finding.

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| R1 AC 1–6: the bottom line first, then a story; three STE rules; plain-language habits; linking sentences kept; one action per step; no STE dictionary, carve-out unchanged | `skills/writing/SKILL.md` carries each rule. T6 parity checks P1–P10 pass. T11: the dogfood self-review applied the skill to this item's own artifacts and found nothing | [verification.md § Test runs](verification.md#test-runs-t1-t2-t6-t10-t12), [self-review.md](self-review.md) |
| R2 AC 1–6: a `## The short version` card on six spec templates and the briefing, with a soft ~120-word guide and three layers; gated sections stay | T6 P5 asserts the card heading on every template. P3 still asserts that no length limit appears | [verification.md § Test runs](verification.md#test-runs-t1-t2-t6-t10-t12) |
| R3 AC 1–7: `design.md` covers Interfaces, Architecture and Technology choices with no code-level detail, and the standing review check | T6 P7 (sections in order) and P9 (standing checks in `reviewing.md`). Self-review round 2 (F1) fixed the summaries elsewhere that still described the old shape | [self-review.md](self-review.md) |
| R3 AC 8: gated sections validate on old-shape and new-shape designs | T10: the `design` node's gated sections were checked on issue-538 (old shape), on this item and on the new template | [verification.md § Test runs](verification.md#test-runs-t1-t2-t6-t10-t12) |
| R3 AC 9: the design-approval request points at Interfaces first | T1: the focus line appears at design-approval only, and other gates' messages are unchanged | same |
| R4 AC 1–5: code comments explain the code; the standing check | `workflow.md` § Code comments and `reviewing.md` § Standing checks. T11 and both review rounds ran the check on this diff and found nothing | [self-review.md](self-review.md), [critic-review.md](critic-review.md) |
| R5 AC 1–4: the Claude doc and artifact act as a reading view | `workflow.md` § A reading view, not a copy. This item's own Claude doc was kept as one tab per spec file, rewritten from the file | [verification.md](verification.md) |
| R6 AC 1–3: review effort and a guided tour in the briefing | T6 P8 checks the briefing template. This PR's own description uses the template | PR #545 description |
| R7 AC 1–3: archify when installed, else mermaid; nothing installed | `explainer.md` § Diagrams in a rich view. T6 checks that the text names no install step | [verification.md § Test runs](verification.md#test-runs-t1-t2-t6-t10-t12) |
| R8 AC 1, 2, 5, 6, 7: checklist rows; frozen and confirmed; dropped without the explainer; off when absent, unreadable or contradictory; Slack treats them as settings | T1 (99 passed) and T2 (3 Gherkin scenarios). Critic C1 made a contradictory row count as off, red → green | [verification.md § Test runs](verification.md#test-runs-t1-t2-t6-t10-t12), [critic-review.md](critic-review.md) |
| R8 AC 3–4: slides and flashcards produced with the explainer | T1: the prompt line appears at `spec-explainer` and `code-explainer` only. T5: the template's Slides and Flashcards tabs work in light, dark and phone width. T9: a 15-step keyboard walk | [verification.md § UI](verification.md#ui-t5), [`ui/`](ui/), [verification.md § Accessibility](verification.md#accessibility-t9) |
| R9 AC 1–3: capability docs, decision record, history left alone | `writing-style.md`, `process-graph.md`, `spec-workflow.md` and `docs/cli/state.md` updated; decision-152 recorded. No historical spec rewritten | [documentation.md](documentation.md) |
| Abuse cases 1–4 | 1: T2 unauthorized scenario. 2: T5 rendered a `<img onerror>` title as text with no dialog; a unit check finds no markup sink. 3: issue-536 tests re-run in T12. 4: T6 guidance check. The security review found nothing | [security-review.md](security-review.md) |
| NFR: no new dependency, plugin-portable, backward compatible | No dependency change in `cli/pyproject.toml`. The rules live in skills and templates. T10 round-trips state without the new key | [verification.md](verification.md) |
