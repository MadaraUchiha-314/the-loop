---
type: evidence
phase: needs-review
workItem: issue-551
---

# Critic review: a session never goes idle unnoticed

> The `critic-review` node's proof. The operator's policy is one critic round. The
> configured critic is `codex` (`gpt-6.1-sol`), a different harness and model family
> from the one that wrote the change.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| — | `codex` | **unavailable** | Ran in the operator's checkout, not this one, and found no branch to review. Does not count. | — |
| — | `codex` | **unavailable** | The client's call to the service timed out before the critic answered. Does not count. | — |
| 1 | `[codex/gpt-6.1-sol]`, in this checkout, 58 s, 64,857 input and 1,778 output tokens | new findings | 3. **C1** (major): a nudge acts on a stale snapshot → fixed, `bf1ddf60`. **C2** (major): an answer recorded mid-cycle loses to a pending default → fixed, `190ceb04`. **C3** (minor): `design.md` lines 149–159 are a file list and lines 280–295 prescribe an algorithm → not fixed: the design is locked at its gate; flagged for the approver. | [comment](https://github.com/MadaraUchiha-314/the-loop/pull/552#issuecomment-7052775070) |

## The fix for C1 and C2

Before each act, the watcher reads that one work item's records again, derives its
state again, and acts only if the same act is still owed for the same node. This
narrows the race to the moment between that read and the record. It does not close
it: the dispatcher and the watcher share no lock and may run in different processes.
Losing that last race means a nudge reaches a session that has just started working,
or a default is recorded a moment after an answer. In the second case the answer
still reaches the session as a comment, and the "proceed with your default" prompt
tells the session to follow a later answer.

## How the round was run

`the-loop critic run codex --root "$PWD" --cwd "$PWD" --prompt-file … --work-item issue-551 --timeout 1500`,
in-process. The prompt carried the change to review, the criteria, both standing
checks, all 34 findings of the two self-review rounds, the recorded limits, and the
output contract.

Two defects of the critic verb showed here and are worth a ticket of their own: it
defaults to the operator's checkout instead of the session's, and its call through
the service times out before a real review finishes.
