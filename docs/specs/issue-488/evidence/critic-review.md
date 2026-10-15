---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#488"
---

# Critic review: the explainer, the spec quiz and the code quiz

> The `critic-review` node's proof: a different model and harness reading the diff. The
> operator's policy is `criticReviewCount: 1`. The critic was given the spec, the ten
> self-review findings (so it would not repeat them), and the open token finding, which
> was already accepted, so it reported other paths.

## Review cycles

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| 1 | `codex/gpt-6.1-sol` (`the-loop critic run codex`: exit 0, 52 s, 64k input tokens, 1.7k output tokens) | 3 new findings | **C1** (high): an authorized edit after an unauthorized tick adopted that tick → fixed `61e4999`, so every editor in the history must be authorized. **C2** (medium): R5.6 was enforced only from quiz posting, not from page publication → fixed `61e4999` with `explainer-postdates-spec`. **C3** (low): the reference's escaping rule was garbled → fixed `bad346d` | [findings and fixes](https://github.com/MadaraUchiha-314/the-loop/pull/489#issuecomment-6202226899) |

**Not converged at zero.** The cap is one round, and that round found problems. All
three are fixed, each with a regression test, and the full suite passed afterwards
(6137). No finding repeated a self-review finding. The C1 fix also tightens S1's
boundary, since an edit history with a stranger in it now fails closed.
