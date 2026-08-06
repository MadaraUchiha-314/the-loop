# Decision 061: Writing for humans is a sibling skill — with no length limits

- **Status:** proposed
- **Date:** 2026-08-06
- **Deciders:** @MadaraUchiha-314 (issue #165, PR #168)
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

**A sibling skill carries the judgement; config carries the policy; the templates point at
the skill; a test carries the drift.**

| Sub-decision | Chosen | Why |
|---|---|---|
| **D1 — a second bundled skill**, `skills/writing/` (`the-loop:writing`), not a `reference/writing.md` | Skill | The ticket asked for a skill, and a skill is separately invocable — an author can run it on a README that has nothing to do with a work item. the-loop's own skill holds no copy of the rules, so there is one source. |
| **D2 — no length limits** | The contract sets shape and register; it sets no word count | See below. |
| **D3 — the density test replaces the word count** | "Can any sentence come out without losing information?" | Scope-independent, and it is what a reviewer actually judges. A 2000-word design that passes it is the right length; a 200-word one that fails it is not. |
| **D4 — concision governs words, not coverage** | A gated section stays, recorded empty with a reason | Deleting `## Security considerations` to shorten a document is fraud, not editing. |
| **D5 — formal registers are carved out** | EARS, abuse cases, RFC-2119, API contracts, schema descriptions | They are testable contracts. Softening one breaks the gate that reads it. |
| **D6 — the test asserts mechanics, not quality** | The skill parses · every human-read template points at it · the pointer names the skill the schema declares · no length limits have returned · no P0 tell in shipped prose | Presence is mechanical; quality is a review item. The prior art reports false-positive rates above 60% on non-native speakers for pattern matching of this kind, so only tells with no legitimate technical reading are asserted. |
| **D7 — draw it rather than describe it** | Three or more named parts → mermaid | `userInteraction.diagramFormat` already *permitted* diagrams; nothing *preferred* them. |

### D2 — why the budgets were removed

This work item first shipped per-artifact word budgets (500 requirements, 900 design, …),
declared in the schema and mirrored by a `<!-- writing: budget=N -->` marker in each
template, advisory rather than blocking. The owner rejected them in review on PR #168:

> We don't know the scope of each work item, so how can we put budgets on requirements.md
> or design.md? Let's not enforce budgets.

That is decisive, and the implementation had already produced the evidence for it. Three
budgets had to be corrected before the change was even merged: `tasks: 200` turned out to
be unreachable from its own empty template (274 words of guidance), and the PR briefing
ran ~530 against 400 while carrying only the education the R10 gate requires. A number
that has to be renegotiated by every artifact that meets it is not a policy — and an
advisory number that is routinely exceeded teaches authors that the ones which matter can
be ignored too.

The failure mode a cap does *not* prevent is the important one: prose moves to an
appendix, a linked document, or a second PR comment, and the reviewer reads the same
words in more places.

So the number goes and the judgement stays. What survives is scope-independent: the
four-part spine, conclusion-first sections, the revise pass, the diagram rule, the formal
carve-out, and the tells catalogue.

## Alternatives considered

- **Per-artifact word budgets.** Shipped first, then rejected — see D2.
- **Budgets scaled by risk tier or diff size.** Rejected as a worse version of the same
  mistake: it makes the number harder to predict without making it more right, and a
  one-line fix to an auth path would get a large design budget for no reason.
- **A prose bullet in `SKILL.md` and nothing else.** Rejected: the bullet effectively
  existed (`prSummary.condensed`) and the specs were still 30 KB. A pointer in every
  template plus a parity test is what makes it reach the author.
- **A graph hook blocking a phase on length.** Rejected twice over — by D2, and because a
  gate that misfires is one people route around (`test_docs_parity`'s own reasoning).
- **A `the-loop writing lint` command.** Deferred: it needs a core → API → client slice
  (decision-058) to earn its place, and with no numbers left there is little for it to
  measure.
- **Rewriting the existing specs to the new style.** Rejected: they are the historical
  record, and editing one to match today's style destroys the evidence it holds.
