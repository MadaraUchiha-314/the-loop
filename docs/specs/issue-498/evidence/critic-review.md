---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#498"
---

# Critic review: a control keyword must open the comment; an ambiguous body is conversation

> The `critic-review` node's proof. Policy (`the-loop critic policy`): one critic round
> with the configured critic `codex` (harness `codex`, model `gpt-6.1-sol`), stop on
> zero new findings. The finding was posted on PR #523, answered reply-first, and fixed
> in one commit.

## Review cycles

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| 1 | codex/gpt-6.1-sol | new findings (1) | [P1] the phase-selection gate's classifier released on any authorized comment *containing* the execute keyword, so a forwarded ambiguous body (`the-loop pause` + `the-loop execute`) could freeze a selection → will-fix → `_says_execute` runs `parse_command` over the deployment's keywords, seeded as `controlKeywords`; four regression tests (14b92cb6). Run: 52.3 s, `--cwd` this worktree | [round 1 on PR #523](https://github.com/MadaraUchiha-314/the-loop/pull/523#issuecomment-6370121944) |

One round is the operator's cap; the finding is fixed, and no second round is run.
