---
type: evidence
workItem: issue-544
---

# Documentation: make what the-loop writes easy to read and review

> The `capability-docs` node's proof. Both sections were updated in PR #545, the same PR
> as the change.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`writing-style.md`](../../../capabilities/writing-style.md) | The writing contract now says: the point first, then a story; three STE rules and plain language; the `## The short version` card with a soft ~120-word guide; `design.md` holds Interfaces, Architecture and Technology choices; the code-comment rule and the standing review checks; review effort and a guided tour in the briefing | issue-544 |
| [`process-graph.md`](../../../capabilities/process-graph.md) | This doc also describes the explainer nodes. It now covers the `explainer-slides` and `explainer-flashcards` rows, `explainerExperiments` frozen only when the explainer runs, and the focus line on the design-approval review request | issue-544 |
| [`spec-workflow.md`](../../../capabilities/spec-workflow.md) | The card on every spec template, the new `design.md` shape, the Slides and Flashcards explainer tabs, and the doc and artifact tabs as a reading view | issue-544 |
| [`docs/cli/state.md`](../../../cli/state.md) | The `explainerExperiments` attribute of `work-item-state.json` | row in the attribute table |
| [decision-152](../../../decisions/decision-152.md) and the [decisions index](../../../decisions/decisions.md) | A new record: the soft card guide sits alongside decision-061's no-length-limits rule, because nothing measures it | new record |

## Documentation

| Document | What changed |
|----------|--------------|
| `skills/writing/SKILL.md` | Rewritten around the point first, then the story: plain language, three layers, linking sentences as information, and what `design.md` leaves out |
| `skills/the-loop/SKILL.md`, `skills/handoff-to-the-loop/SKILL.md` | The new `design.md` sections wherever they are summarised |
| `skills/the-loop/reference/workflow.md` | § Code comments, § A reading view, not a copy, the briefing summary and the `design.md` description |
| `skills/the-loop/reference/reviewing.md` | § Standing checks, which every self-review, critic and design-critic prompt now includes |
| `skills/the-loop/reference/explainer.md` | § Experiments: slides and flashcards, and § Diagrams in a rich view (archify, then native drawing, then mermaid) |
| `skills/the-loop/reference/collaboration.md` | The briefing now asks for a review-effort score and a guided tour of the diff |
| `commands/create-design.md`, `commands/work-on.md`, `commands/execute-tasks.md` | The new `design.md` sections and the briefing's guided tour |
| `skills/the-loop/templates/*` | A card on every spec template and on the briefing; `design.md` reshaped; the Slides and Flashcards tabs in `explainer.html`; an Experiments row in the explainer records |

No historical spec under `docs/specs/` was rewritten (R9 AC 3).
