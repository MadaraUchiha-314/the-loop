# Decision 061: Writing for humans is a sibling skill with per-artifact budgets — advisory, never a gate

- **Status:** proposed
- **Date:** 2026-08-06
- **Deciders:** @MadaraUchiha-314 (issue #165)
- **Work item:** issue-165
- **Spec:** `docs/specs/issue-165/`

## Context

[Issue #165](https://github.com/MadaraUchiha-314/the-loop/issues/165): the-loop's artifacts
are verbose, formal where they need not be, and describe in prose what a diagram would
show. `docs/specs/issue-163/requirements.md` is 30 KB. The reviewer's job is to say yes or
no, and the document makes them read an essay first.

Two forces produced that, both intentional. Every phase gate demands a section, so an
artifact grows one per gate whether or not that gate has anything to say. And the only
verbosity lever the harness had — `tokenEconomy.outputVerbosity` — compresses **chat
narration** and explicitly *preserves* `specs`, so it is aimed away from the documents the
reviewer opens.

## Decision

**A sibling skill carries the judgement; config carries the policy; the templates carry
the number; a test carries the drift.**

| Sub-decision | Chosen | Why |
|---|---|---|
| **D1 — a second bundled skill**, `skills/writing/` (`the-loop:writing`), not a `reference/writing.md` | Skill | The ticket asked for a skill, and a skill is separately invocable — an author can run it on a README that has nothing to do with a work item. The-loop's own skill holds no copy of the rules, so there is one source. |
| **D2 — budgets are advisory** | Over budget is a review comment, never a blocked phase | Readability is a judgement. `test_docs_parity` already reasons that a gate which misfires is one people route around, and a blocking budget would be met by moving prose into an appendix. |
| **D3 — budgets count prose only** | Front matter, headings, tables, code, mermaid and EARS excluded | Otherwise the budget argues against the diagram it exists to encourage, and the writing rule fights the requirements gate. |
| **D4 — brevity governs words, not coverage** | A gated section stays, recorded empty with a reason | Deleting `## Security considerations` to make a budget is fraud, not editing. |
| **D5 — formal registers are carved out** | EARS, abuse cases, RFC-2119, API contracts, schema descriptions | They are testable contracts. Softening one breaks the gate that reads it. |
| **D6 — the test asserts mechanics, not quality** | Skill present · markers well-formed · markers ↔ schema defaults both ways · skill and every template within their own budgets · no P0 tell | Presence is mechanical; quality is a review item. The prior art reports false-positive rates above 60% on non-native speakers for pattern matching of this kind, so only tells with no legitimate technical reading are asserted. |
| **D7 — draw it rather than describe it** | Three or more named parts → mermaid | `userInteraction.diagramFormat` already *permitted* diagrams; nothing *preferred* them. |

## Alternatives considered

- **A prose bullet in `SKILL.md` and nothing else.** Cheapest. Rejected: the bullet
  effectively existed (`prSummary.condensed`) and the specs were still 30 KB. Unenforced
  prose is what issue-148 cost.
- **A graph hook blocking a phase on word count.** Rejected as D2.
- **A `the-loop writing lint` command.** Deferred: it needs a core → API → client slice
  (decision-058) to earn its place, and nothing yet says the test is insufficient.
- **Rewriting the existing specs to the new style.** Rejected: they are the historical
  record, and editing one to match today's style destroys the evidence it holds.
