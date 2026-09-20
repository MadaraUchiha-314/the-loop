---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#396"
---

# Self-review: `graph status` reads the state file the runtime wrote (issue-396)

> `the-loop critic policy` on this machine: `selfReviewCount: 3`, `criticReviewCount: 3`,
> but `critics: []` in this repo's `cli-config.yaml` — the critic rounds are
> **unavailable** and do not count. The self-review read the diff adversarially in
> three passes; round 3 found nothing new, which is the stop rule.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | self (diff read) | new findings | (a) the first resolver returned two shapes (`Path` or `(Path, note)`) and pyright rejected every caller → split into `_resolve_root` and `_resolve_read_root`; (b) three new scenario tests asserted `ok` where a fresh state honestly reads `UNMET` (phase-selection still waiting) and asserted the refusal on `outcome` where the envelope carries it on `status` → the tests were wrong, not the code; fixed | this PR |
| 2 | self (behaviour read) | new findings | (c) the not-found hint said "run from the work item's checkout" whenever the state *directory* was absent — for an inner loop that has not started, `pr-loops/pr-<n>/` is absent inside the right checkout, so the imperative was a misdirection → reworded as a question (`is this the work item's checkout?`), documented as such; (d) the mutating verbs' `state_lock` creates `docs/specs/<id>/` in the working directory before refusing a never-entered item — pre-existing, out of scope, the test only asserts no state file is written; (e) `work_item_id` strips whitespace where the old path passed it verbatim — harmless (a padded id never resolved) and matches `derive_ref` | design.md § Error handling |
| 3 | self | zero (converged) | — | — |
| — | critic | unavailable | `critics: []` — no critic harness configured in this repo's CLI config | `.the-loop/cli-config.yaml` |

## Process note

The work item was driven by labels and the spec chain, as issue-395 was: this checkout's
graph state (`work-item-state.json`) was not written because the outer loop's first node,
`phase-selection`, is a human gate this session may not answer.
