---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#498"
---

# Self-review: a control keyword must open the comment; an ambiguous body is conversation

> The `self-review` node's proof. Policy (`the-loop critic policy`): two self rounds,
> stop on zero new findings, escalate on a repeated finding. Both rounds were posted on
> PR #523.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | claude/opus-5.5 | new findings (2) | 1 poller docstring line over-long → will-fix → reflowed (9c30f1d6). 2 `relay_body` no longer quotes the words, so a pasted HTML comment renders unquoted → won't-fix: the quoted form never stripped it either, and a pasted self-marker fails closed. Two checks with no change: ambiguity covers custom keywords; the ambiguous path is the command-free path (scope, pause) | [round 1](https://github.com/MadaraUchiha-314/the-loop/pull/523#issuecomment-6369862288) |
| 2 | claude/opus-5.5 | zero (converged) | none | [round 2](https://github.com/MadaraUchiha-314/the-loop/pull/523#issuecomment-6369866960) |
