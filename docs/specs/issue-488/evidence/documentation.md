---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#488"
---

# Documentation: the explainer, the spec quiz and the code quiz

> The `capability-docs` node's proof. Everything listed here changed in PR #489, the
> same PR as the code.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`process-graph.md`](../../../capabilities/process-graph.md) | The four nodes, the `explainer` skip set and settings row, and the quiz-gate contract, restated after review: authorship, the whole edit history, Jira's typed line, `micro` depth, per-tick dedup, re-posting, and `explainer-postdates-spec` (R5.6). Also `not-offered` skips and the `quiz_attestation` doorbell | issue-488 row, extended with the review hardening |
| [`spec-workflow.md`](../../../capabilities/spec-workflow.md) | The explainer and the quizzes as part of the spec chain: the depth ladder, the publishing modes, and on by default | issue-488 row |

## Documentation

| Document | What changed |
|----------|--------------|
| `skills/the-loop/reference/explainer.md` (new) | The agent's procedure: depth ladder, section contract, quiz rules, publishing table, and "never tick an attestation box". Since review, it also covers the `Depth` row that decides the line, committing the record (R5.6), and the corrected `<` escaping rule |
| `commands/explain.md` (new) | `/the-loop:explain`, branching on `spec-explainer` / `code-explainer` |
| `skills/the-loop/SKILL.md`, `reference/workflow.md` | The chain section, one operating-principles bullet, and a new section "The explainer and the quizzes" |
| `skills/the-loop/templates/explainer.html`, `templates/evidence/spec-explainer.md`, `templates/evidence/explainer.md` (new) | The page template, with the engine rendering through `textContent` only, and the two record templates |
| `skills/the-loop/templates/pr-briefing.md` | A "Start here: the explainer" line |
| `docs/cli/commands/graph.md`, `docs/reference/commands.md`, `docs/.vitepress/config.mts` | The checklist's settings row, and the new command in the reference and the nav |
| `docs/decisions/decision-143.md` + index row | Ticks are attributable for quiz gates, through GraphQL `userContentEdits` |
| `README.md` | The flow diagram shows the two quizzes |
| `ui/src/demo/fixture.ts` | The demo's outer-loop node list |
