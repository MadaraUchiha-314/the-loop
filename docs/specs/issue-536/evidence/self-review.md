---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#536"
---

# Self-review: publish a work item's spec chain as one Claude doc

> Policy (`the-loop critic policy`): `selfReviewCount: 2`, `stopOnNoNewFindings: true`.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | claude/claude-opus-5-5 (author session) | new findings | **F1** a doc quiz tab with the answers under a closing heading shows them to anyone who scrolls (the artifact hides them with a script) → fixed: the answers go in a separate last tab, "Quiz answers" (`reference/explainer.md`, design rule 2). **F2** an untouched Slack Execute press carries no rows, so it reads both rows as unticked → no change: it already behaves this way for `claude-artifact`, and the Slack note says these settings keep the deployment's defaults; not a regression. **F3** on a deployment whose default harness is not `claude`, the new ticked default produces "Not applied: `claude-doc`" in every untouched confirmation → no change: the artifact's ticked default did the same, and the confirmation names it. | PR #537 |
| 2 | claude/claude-opus-5-5 (author session) | zero (converged) | Re-read the diff against R1–R4 and the abuse cases: the parse is exact-token, the conflict rule is applied before the harness rule, the state collapses both-true, the key is written only when true, and the prompt line is a constant. The skill text covers R4.3–R4.7. No new findings. | PR #537 |

## Requirement coverage of the skill text (R4.3–R4.7)

| Requirement | Where |
|---|---|
| R4.3 procedure | `reference/workflow.md` § The spec chain as one Claude doc, rules 1, 4, 5 |
| R4.4 explainer/quiz as tabs | rule 2; `reference/explainer.md` § Publishing; `commands/explain.md` |
| R4.5 read before rewrite | rule 3; `SKILL.md` bullet; the prompt line |
| R4.6 feedback, never a gate answer | rule 6; `reference/collaboration.md` |
| R4.7 no connector | rule 8; the prompt line |
