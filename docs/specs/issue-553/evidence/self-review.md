---
type: evidence
phase: needs-review
workItem: issue-553
---

# Self-review: a context-gathering phase before the spec chain

> The `self-review` node's proof. The policy read with `the-loop critic policy` allows
> two rounds and stops on a round with no new finding.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | claude/claude-fable-5-2 (the authoring session) | new findings | S1–S4 below: two fixed, two accepted with a reason | [PR #554](https://github.com/MadaraUchiha-314/the-loop/pull/554) |
| 2 | claude/claude-fable-5-2 (the authoring session) | zero (converged) | re-read the runtime guard, the stage-fit rule and the prompt renderer against the abuse-case table; nothing new | [PR #554](https://github.com/MadaraUchiha-314/the-loop/pull/554) |

## Findings

- **S1 — the decision record listed alternatives nobody weighed.** `decision-156.md`
  named `understanding.md` and `as-is.md` as considered. The approved brainstorm
  records only two rejected options. *Fixed:* the bullet is removed.
- **S2 — a new test read an attribute of a value that may be `None`.** Pyright flagged
  it in `test_graphlink_integration.py`. *Fixed:* the test narrows the value first.
- **S3 — the frozen graph record does not learn of a demotion.** `work-item-state.json`
  keeps the graph as frozen at selection, with `context-gathering` marked skipped. When
  a failed `current-state.md` then selects that node, the record still says skipped.
  *Accepted:* the same is true today of every node a demotion un-skips; routing reads
  `skips` and `optIns`, not that record. `handoffDemoted` and the `optIns` entry
  (`via: handoff-demotion`) say what happened.
- **S4 — a demotion to the start names the two context nodes in its un-skip list.**
  With no file verified, the list starts at the node after `import-handoff`, which is
  now `context-gathering`. *Accepted:* un-skipping removes a declared skip, and an
  unselected opt-in node holds none, so the names change nothing. Two tests pin it.

## What the review could not see

The `graph show` sample in `docs/cli/commands/graph.md` was written from the graph
file, not copied from a run: the CLI on this machine answers from the running daemon,
which has the released graph. The loader in this branch returns the new node order.
