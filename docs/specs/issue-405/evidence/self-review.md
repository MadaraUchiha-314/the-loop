---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#405"
---

# Self-review: the clause reader stops at the phases; the close path waits for the endgame (issue-405)

> `the-loop critic policy` on this machine: `selfReviewCount: 3`, `criticReviewCount: 3`,
> but `critics: []` in this repo's `cli-config.yaml` — the critic rounds are
> **unavailable** and do not count. The self-review read the diff adversarially in
> three passes; round 3 found nothing new, which is the stop rule.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | self (diff read) | new findings | (a) the first P2 test asserted the harness ended **exactly once** and the record listed as `closed`; the authorized closer's cleanup ends the harness a second time (the retain path agreeing with the close path — pre-existing, documented in `_retain_endpoint`) and removes the record, so the tests were wrong, not the code → assert "ended, at least once" and "no live record"; (b) a test subclass overriding `FakeTmux.has_live_session` tripped pyright's `Literal[True]` inference → a `monkeypatch` on the instance; (c) the loop-of-dicts test case let pyright infer `grace: None` → explicit tuples | this PR |
| 2 | self (behaviour read) | new findings | (d) `_defer_close` held a closure for a **paused** session too (`is_live` is active-or-paused) — kept, deliberately: the hold is bounded and a paused session's pane is still the one the operator may resume to finish; documented in the docstring's conditions; (e) `_close_ended_session` reads the graph context on the **immediate** path too, for `merged` — one more `git config` subprocess per closure, beside the two the close already makes; accepted for the cosmetic the report asked for; (f) `read` on the drop record and the `info` log carry the operator's own message text — on the operator's machine, in the process log the report itself asked for; the event-log field carries names only | design.md § Trade-offs |
| 3 | self | zero (converged) | — | — |
| — | critic | unavailable | `critics: []` — no critic harness configured in this repo's CLI config | `.the-loop/cli-config.yaml` |

## Process note

The work item was driven by labels and the spec chain, as issue-395 and issue-396 were:
this checkout's graph state (`work-item-state.json`) was not written because the outer
loop's first node, `phase-selection`, is a human gate this session may not answer.
