---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#488"
---

# Self-review: the explainer, the spec quiz and the code quiz

> The `self-review` node's proof. One row per round, per `reference/reviewing.md`. The
> operator's policy (`the-loop critic policy`) is `selfReviewCount: 2`,
> `stopOnNoNewFindings: true`, `escalateOnRepeatFinding: true`.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | `[claude/opus-5.5]`, a fresh-context reviewer over `main...HEAD` and the spec | 7 new findings | **S1** (high), a look-alike quiz comment could force `stale` or hide the real tick → fixed `e9138f7`. **S2** (medium), a re-tick after a refusal was swallowed by the dedup → fixed `d39e767`. **S3** (medium), a failed post left a gate with no box → fixed `4b25723`. **S4** (medium), Jira could never pass a tick → fixed `bdcbd15`. **S5** (low), no `graph.quiz_refused` → fixed `e179176`. **S6** (low), R2.7's `micro` line was missing → fixed `a8f94f4`. **S7** (low), no digest check in the typed fallback → won't-fix, because a stale own comment returns `stale` first | [findings](https://github.com/MadaraUchiha-314/the-loop/pull/489#issuecomment-6201486989), [fixes](https://github.com/MadaraUchiha-314/the-loop/pull/489#issuecomment-6201696371) |
| 2 | `[claude/opus-5.5]`, a fresh-context reviewer given round 1's findings | 3 new findings (cap reached) | **S8** (high, Jira only), the quiz marker was dropped by Jira's format → fixed `3e247f5`. **S9** (medium), S2's release made a refused tick ring every poll cycle → fixed `7625e13`. **S10** (low), the read-only line passed a standard-depth quiz → fixed `af8793a`. The capability doc was brought in line in `c31ae66` | [findings](https://github.com/MadaraUchiha-314/the-loop/pull/489#issuecomment-6201767950) |

**No repeated finding.** S9 is a regression that S2's fix introduced, not S2 raised again.
It is fixed, and the test pins the behaviour both fixes need.

**The rounds stopped at the cap, not at zero findings.** Round 2 still found problems,
and the policy allows no third self-review round. The critic round reviews the code after
these fixes and receives all ten findings, so it adds new ones rather than repeating them.

**Every fix has a test that fails without it** (S1 and S2 were checked by reverting the
source file). After the last fix: 6133 tests passed, and lint, pyright, format and
validate were clean.
