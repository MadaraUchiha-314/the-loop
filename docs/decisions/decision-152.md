<!-- Written per the `the-loop:writing` skill. -->

# Decision 152: Story-first, layered artifacts, a design held at the level of decisions, and comments that explain the code

- **Status:** proposed (the owner decides at the PR)
- **Date:** 2026-11-18
- **Deciders:** MadaraUchiha-314 (the brainstorm answers, the requirements review comment
  on `design.md`, the approvals), the-loop (the mechanism)
- **Work item:** [issue-544](https://github.com/MadaraUchiha-314/the-loop/issues/544)
- **Spec:** [`docs/specs/issue-544/`](../specs/issue-544/)
- **Refines:** [decision-061](decision-061.md): there is still no word limit on any
  artifact. The new card carries a soft guide of about 120 words that nothing measures.

## The short version

the-loop's specs were accurate but hard to read: long, dense, with no story, and with the
*how* mixed into the *what*. We changed how much a reviewer must read before deciding, then
how it reads. Every human-read artifact opens with a card (`## The short version`). The
writing skill asks for the bottom line first and then a story, in plain language with
three rules borrowed from Simplified Technical English. `design.md` holds interfaces,
architecture and technology choices, and no code-level detail. Production-code comments
explain the code and cite no process.

## Context

Recent work items wrote 1,100–2,800 words per spec file, four or five files each.
Reviewers skimmed. The writing skill optimised for density, which cut the linking words
that make an argument easy to follow. The `design.md` template invited function names,
data models and error-handling detail that the approver did not need. And 23% of the
CLI's comment lines cited an issue, decision, requirement or critic rather than
explaining the code.

decision-061 rejected checked word budgets, because a work item's scope is not known in
advance. That reasoning still holds for whole documents.

## Decision

1. **Three layers.** Card, story, reference. The card opens every human-read spec
   template and the PR briefing under the fixed heading `## The short version`, which a
   parity test checks.
2. **A soft card guide, not a limit.** About 120 words. A card does not grow with the
   change, so a guide fits it where decision-061's objection to limits does not apply.
   No test, gate or hook measures it.
3. **Plain language, borrowed rules.** Sentences of about 25 words, one idea each, no
   stack of more than three nouns, plus plain-language habits. The STE dictionary is not
   adopted. A linking sentence counts as information.
4. **`design.md` at the level of decisions.** Interfaces, Architecture, Technology
   choices, then Security design and Testing strategy. No function or method names,
   signatures, class layouts, algorithms, code snippets, internal data structures or
   file-by-file change lists. The gated sections are unchanged, so old designs still
   validate.
5. **Comments explain the code.** No work-item, decision or requirement ids, review
   rounds or spec files in production-code comments. Traceability goes in commits, the
   PR and the specs. Test docstrings keep their `Requirement:` links. Going forward only;
   the ~2,000 existing lines are not swept by this decision.
6. **Enforced by review, not a linter.** Both rules are standing checks in every
   self-review and critic prompt.
7. **The PR briefing** gains a 1–5 review-effort score and a guided tour of the diff.
8. **Experiments are opt-in.** Slides and flashcards are unticked rows under `explainer`
   and need it ticked.

## Consequences

- A reviewer can stop after the card. The cost moves to the author, who must state the
  point before the detail.
- `design.md` is shorter and approves decisions. Implementation detail is reviewed where
  it lives, in `tasks.md` and the diff.
- New comments read without the ticket history. Old comments still cite the process
  until a separate sweep, so the codebase carries two styles for a while.
- Review enforcement depends on reviewers running the standing checks. A linter would be
  stricter, but comment syntax varies across consuming projects and a lint would flag
  every untouched historical line.

## Alternatives considered

- **Adopt full Simplified Technical English.** Rejected: built for procedures, stilted
  for rationale, and its dictionary fights technical vocabulary.
- **Make HTML the source of truth.** Rejected: gates, locks and PR diffs read markdown.
  The Claude doc and artifact stay reading views.
- **Word limits per file.** Rejected again, for decision-061's reason. Only the card has
  a guide, and it is not checked.
- **Split `design.md` into a contract part and an internals part.** Proposed in the
  brainstorm, replaced at the requirements review: the internals do not belong in the
  design at all.
- **A comment linter.** Rejected for now; see Consequences.
