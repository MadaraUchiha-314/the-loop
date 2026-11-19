---
type: evidence
phase: needs-review
workItem: "issue-544"
---

<!-- Written per the `the-loop:writing` skill. -->

# Self-review: make what the-loop writes easy to read and review

## The short version

Round 1 is the dogfood review the testing plan asks for (T11). It applies the two new
standing checks to this PR, and checks that this work item's own artifacts follow the
new guidance. Both checks came back clean. The `self-review` node adds its rounds below.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 (T11, at verification) | [claude/opus-5.5] | zero | **Comments:** every production-code comment the diff adds or changes under `cli/the_loop/` was read; none cites an issue, decision, requirement id, review round or spec file. **Design level:** `design.md` holds interfaces (the checklist rows, the state key, the prompt line), architecture and technology choices; no function or method names, signatures, class layouts, algorithms, code snippets or file-by-file lists. **Guidance applied:** `brainstorm.md`, `requirements.md`, `design.md`, `testing-plan.md` and `tasks.md` each open with `## The short version`, and the design follows the new section order. | this file |
| 2 (self-review node) | [claude/opus-5.5] | new findings | **F1 — stale design shape:** five places still described `design.md` as overview, components, data models and error handling: `commands/create-design.md`, `commands/work-on.md`, `skills/the-loop/SKILL.md`, `reference/workflow.md` § The spec artifacts, and the handoff skill's section table, which also lacked the card. → will-fix, fixed in the next commit (the card, interfaces, architecture, technology choices, no code-level detail). Also checked with no finding: the experiment rows read as settings on the checklist, in Slack and in the Jira goldens; a ticked experiment with `explainer` unticked is dropped and reported; the template engine assigns no markup; the explainer record templates carry the Experiments line. | this file |

Round 2 is the last round `the-loop critic policy` allows (`selfReviewCount: 2`). Its one
finding is fixed, so nothing is carried to the critic round.
