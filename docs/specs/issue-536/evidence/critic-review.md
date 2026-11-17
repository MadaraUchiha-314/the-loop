---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#536"
---

# Critic review: publish a work item's spec chain as one Claude doc

> Policy (`the-loop critic policy`): `criticReviewCount: 1`. Run with
> `the-loop critic run codex --root . --cwd <this worktree>` against
> `git diff origin/main...HEAD`.

## Review cycles

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| — | codex/gpt-6.1-sol | unavailable | Ran in the operator's default checkout, where the branch does not exist, and reviewed nothing. Not counted; re-run with `--cwd` set to this worktree. | — |
| 1 | codex/gpt-6.1-sol | new findings | **C1 (medium)** `reference/explainer.md` publishing table: with `claudeDoc: true`, an artifact tool and no Docs connector, no row applied, so the explainer could go unpublished and block its node → fixed in the commit after the self-review record: the standalone-artifact row now applies whenever no row above did, and the HTML row whenever no row above did and there is no artifact tool. | PR #537 |

The round cap (1) is reached. C1 was a gap in skill text, fixed directly and unambiguously, so no second round was needed.
