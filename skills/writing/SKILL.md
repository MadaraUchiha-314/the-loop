---
name: writing
description: How the-loop writes for a human reader. Use when authoring or revising any artifact a person will read — requirements.md, design.md, testing-plan.md, tasks.md, a PR briefing or PR description, a decision record, a capability doc, a ticket or review comment, a README. Carries the document spine, the per-artifact word budgets, the prefer-a-diagram rule, the formal-language carve-out that keeps EARS and API contracts intact, and a revise pass for cutting a draft down. Not for code, code comments, log messages or test names.
---

<!-- writing: budget=600 skill=the-loop:writing -->

# Writing for a human reader

A reviewer's job is to say yes or no. Every word between them and that decision is a cost
you are charging them. Write to be approved, not to be admired.

> **The rule:** say it once, to a named reader, in the fewest words that survive review.

## Who is reading

Name the reader before the first sentence. A reviewer of `design.md` knows the codebase
and wants the shape of the change. A `capability.md` reader wants current behaviour and
does not care how it arrived. A ticket comment is read on a phone. The same fact is a
paragraph for one and a table row for another.

## The spine

Every explanatory document answers four questions, in this order:

1. **What was broken** — the situation, and why it mattered enough to open a ticket.
2. **What we did about it** — the resolution, stated as a decision, not a tour.
3. **What it costs** — the trade-off taken, the thing given up, the risk carried.
4. **What to check** — where the reader should look first, and what would falsify it.

Front-load each one. A section's first sentence carries its conclusion; the rest is
support the reader may skip. Read only the first sentence of every section — if that alone
tells the story, the document is shaped right.

## Budgets

Each template declares its prose budget in a marker near the top:

```markdown
<!-- writing: budget=500 skill=the-loop:writing -->
```

Defaults live in `userInteraction.writingStyle.budgets`. A budget counts **prose** —
front-matter, headings, tables, code, mermaid and EARS criteria are free, because the
budget must never argue against a diagram or a contract.

Budgets are **advisory**. Over budget is a review comment, never a blocked phase. But cut
before you justify: three cuts nearly always get there — the sentence restating the
heading, the sentence restating the previous sentence, and the adjective that a number
would replace.

**Brevity is about words, not coverage.** A gated section stays even when it is empty; say
so in one sentence and why. Deleting `## Security considerations` to make a budget is
fraud, not editing.

## Prefer a diagram

Describing a structure, a sequence or a state change with three or more named parts? Draw
it. Mermaid, per `userInteraction.diagramFormat`. Then let the prose say only what the
diagram cannot — why the arrow points that way, what happens when it fails. `design.md`
carries at least one.

## Keep the formal register where it is a contract

These are testable artifacts, not prose, and this skill does not touch them:

- EARS acceptance criteria and abuse cases (`WHEN … THEN the system SHALL …`)
- RFC-2119 keywords in a specification
- OpenAPI / GraphQL contracts and JSON-Schema `description` values
- Quoted material, third-party text, committed evidence and code

Listed in `userInteraction.writingStyle.formalRegisters`. Explanation *around* them is
ordinary prose and follows this skill.

## The revise pass

Draft first, cut second — never both at once.

1. Delete every opener that clears the throat before the point.
2. Delete every sentence the reader could reconstruct from the one before it.
3. Replace each evaluative adjective with the number or example behind it.
4. Convert any run of prose that is really a list, a table or a diagram.
5. Count against the budget. Still over? Something is in the wrong document — move it.

For the catalogue of writing tells and what to do about each,
read [`reference/tells.md`](reference/tells.md).

## Related

`tokenEconomy.outputVerbosity` compresses **chat narration** and preserves specs; this
skill governs the **artifacts**. Third-party skills covering neighbouring ground are
registered in `externalTools`, not vendored (decision-005).
