---
type: evidence
workItem: issue-553
---

# Critic review: a context-gathering phase before the spec chain

> The `critic-review` node's proof. The policy read with `the-loop critic policy` asks
> for one counted round.

## Review cycles

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| — | `codex/gpt-6.1-sol` | unavailable | ran in another repository's checkout and reviewed nothing; not counted | [PR #554](https://github.com/MadaraUchiha-314/the-loop/pull/554) |
| 1 | `codex/gpt-6.1-sol` | new findings | C1 declined with a reason; C2, C3, C4 fixed, one commit each | [PR #554](https://github.com/MadaraUchiha-314/the-loop/pull/554) |

## Findings

- **C1 (major, declined) — ticking only `context-approval` passes the gate even when a
  `current-state.md` is on disk.** True, and it is what Requirement 1.5 asks for: with
  `context-gathering` not selected, the walk goes on to `brainstorming`. A file gathered
  on the developer's machine reaches the gate through a handoff at *Context settled*,
  which enters at the gate. Left as approved; raised to the reviewer in the briefing.
- **C2 (major, fixed) — a handoff that enters at the gate could never be approved.**
  The critic described it as the gate being skipped. Reproduced differently: the gate
  did not move on, but it also could not be answered. Its classifier read the file as
  absent because the authoring node was skipped, the chain then produced an outcome
  the gate has no edge for, and the work item escalated. The same defect held for a
  *brainstorm settled* handoff since issue-517. Fixed in `classify-feedback`: a gate
  that was entered classifies its subject. One test walks both gates: wait, question,
  unauthorized approval, then the author's approval locks the file.
- **C3 (minor, fixed) — a handoff entering at the gate kept the label
  `loop:phase-selection`.** The gate now declares the phase `context-gathering`. This
  departs from the design, which gave the gate no phase; Requirement 1.6 decides it.
- **C4 (minor, fixed) — a file the daemon cannot read was still named in the prompt.**
  The existence check now also asks for read access. One test.

## After the fixes

`make check` exits 0: 7982 passed, 2 skipped. The round is not repeated: the policy
asks for one.
