---
name: writing
description: How the-loop writes for a human reader. Use when authoring or revising any artifact a person will read — requirements.md, design.md, testing-plan.md, tasks.md, a PR briefing or PR description, a decision record, a capability doc, a ticket or review comment, a README. Carries the bottom-line-first story, plain language with three rules borrowed from Simplified Technical English, the three layers (card, story, reference), the prefer-a-diagram rule, what design.md leaves out, the formal-language carve-out that keeps EARS and API contracts intact, and a revise pass. Not for code, log messages or test names; code comments follow the comment rule in the the-loop skill's workflow reference.
---

# Writing for a human reader

A reviewer's job is to say yes or no. Every word between them and that decision is a cost
you charge them. So write to be understood on one read: the point first, then the story
that makes it believable.

> **The rule:** tell one named reader what changed and why, in plain words, then let them
> stop.

## Who is reading

Name the reader before the first sentence. A reviewer of `design.md` knows the codebase
and wants the shape of the change. A `capability.md` reader wants current behaviour and
does not care how it arrived. A ticket comment is read on a phone. The same fact is a
paragraph for one and a table row for another.

## The point first, then the story

Open with the bottom line: the decision, and what you want from the reader. Then tell the
reasoning as a story, in connected sentences. A story links its facts with *because*,
*so* and *which means*. A bullet list drops those words, and the reader has to rebuild
the argument alone.

Every explanatory document answers four questions, in this order:

1. **What was broken**: the situation, and why it mattered enough to open a ticket.
2. **What we did about it**: the resolution, stated as a decision, not a tour.
3. **What it costs**: the trade-off taken, the thing given up, the risk carried.
4. **What to check**: where the reader should look first, and what would falsify it.

Front-load each section. Its first sentence carries its conclusion, and the rest is
support the reader may skip. Read only the first sentence of every section. If that alone
tells the story, the document is shaped right.

## Plain language

Three rules come from Simplified Technical English (ASD-STE100). Take these rules only.
The STE dictionary of approved words does not apply, because technical vocabulary is the
point of a technical document.

- **Keep a sentence to about 25 words.** Split a longer one at its "and" or "which".
- **Put one idea in each sentence.**
- **Never stack more than three nouns.** "Work-item state graph node outcome" becomes
  "the outcome of a node in the work item's graph".

Add the plain-language habits:

- Write to "you" where a reader acts.
- Use the present tense for how things work.
- Prefer the short, common word: "use", not "utilise".
- Keep verbs as verbs: "we decided", not "a decision was made".

**Numbered steps** (testing-plan activities, tasks, runbooks) take one action per step,
in the imperative: "Run `make check`", not "`make check` should be run".

## Three layers

Write every artifact a reviewer approves in three layers. Each layer is complete on its
own, so the reader stops when they have enough to decide.

| Layer | What it holds | Where |
|---|---|---|
| **Card** | what changes, why, and what to check; a diagram when there are three or more named parts | `## The short version`, first section |
| **Story** | the decisions and their reasons, as connected prose | the body |
| **Reference** | detail only some readers need: tables, full lists, edge cases | the end, or a collapsed `<details>` block |

Aim for a card of about 120 words. That is a guide, not a limit, and nothing measures it.
A card does not grow with the change, so a guide fits it where a limit on the whole
document would not.

The layers change order and emphasis, not coverage. A gated section stays under its own
heading, even when its detail is reference material.

## Length follows the change

**There is no word limit, and there should not be.** A two-line bug fix and a new
subsystem are both `design.md`, and a number that fits one is wrong for the other. A cap
would only teach you to move prose into an appendix.

The test is not length, it is **density**: can any sentence come out without losing
information? While the answer is yes, the document is too long, at 200 words or at 2000.
Three cuts nearly always find the slack: the sentence restating the heading, the sentence
restating the sentence before it, and the adjective a number would replace.

**A linking sentence is information.** A sentence that joins two ideas with "because",
"so" or "which means" carries the argument, so the density test never cuts it for length.

**Concision is about words, not coverage.** A gated section stays even when it is empty.
Say so in one sentence, and why. Deleting `## Security considerations` to shorten a
document is fraud, not editing.

## Prefer a diagram

Describing a structure, a sequence or a state change with three or more named parts? Draw
it, in mermaid. Then let the prose say only what the diagram cannot: why the arrow points
that way, and what happens when it fails. `design.md` carries at least one diagram, and
the card carries or links one when the change has three or more parts.

## What `design.md` leaves out

`design.md` is for the decisions a reviewer approves: the interfaces, the architecture
and the technology choices. It carries no function or method names, signatures, class
layouts, algorithms, code snippets, internal data structures or file-by-file change
lists. That detail belongs in `tasks.md` and in the code, where it is reviewed as code.

## Keep the formal register where it is a contract

These are testable artifacts, not prose, and this skill does not touch them:

- EARS acceptance criteria and abuse cases (`WHEN … THEN the system SHALL …`)
- RFC-2119 keywords in a specification
- OpenAPI / GraphQL contracts and JSON-Schema `description` values
- Quoted material, third-party text, committed evidence and code

These are the formal registers of the writing contract (fixed since issue-352).
Explanation *around* them is ordinary prose and follows this skill.

## The revise pass

Draft first, cut second, never both at once.

1. Delete every opener that clears the throat before the point.
2. Delete every sentence the reader could rebuild from the one before it.
3. Replace each evaluative adjective with the number or example behind it.
4. Turn any run of prose that is really a list, a table or a diagram into one.
5. Split each sentence over about 25 words, and each sentence holding two ideas.
6. Read the first sentence of each section in order. If that alone tells the story, stop.
   If it does not, the problem is the structure, not the wording.

For the catalogue of writing tells and what to do about each,
read [`reference/tells.md`](reference/tells.md).

## Related

The token-economy verbosity rule (`the-loop` skill, `reference/token-economy.md`)
compresses **chat narration** and preserves specs; this skill governs the
**artifacts**. Code comments follow the comment rule in the `the-loop` skill's
`reference/workflow.md`. Third-party skills covering neighbouring ground are implemented
natively, not vendored (decision-005, decision-062).
