---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# Self-review: introducing the-loop gateway

> The `self-review` node's proof, one row per round, per `reference/reviewing.md`. The
> operator's policy (`the-loop critic policy`) is `selfReviewCount: 2`,
> `stopOnNoNewFindings: true`, `escalateOnRepeatFinding: true`. The four defects the
> live proof (T4/T11) found were fixed during verification and are not re-listed here.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | `[claude/fable-5.1]`, the implementing session, over `origin/main...e5e0865` and the locked spec, read by risk (store commit/advance/expire, consume refusals, subject resolution and dedup keys, signature paths, exposure guard, client fetch/commit, shutdown) | 4 new findings | **S1** (low): a work item's end settles its delivery only after the 120 s in-flight grace → won't-fix, follow-up for the dispatcher. **S2** (low): Slack's verification `token` stored with every envelope → will-fix, `6a60b0f` (stripped at ingest, test for both transports). **S3** (low): `Store.wake_all` is one-way → won't-fix, process lifetime. **S4** (low): a refused peer logs a warning per back-off retry → won't-fix, the rate is capped and the record is the signal | [round 1](https://github.com/MadaraUchiha-314/the-loop/pull/499#issuecomment-6271134468) |
| 2 | `[claude/fable-5.1]`, a fresh-context reviewer (subagent) given round 1's findings, over `origin/main...6a60b0f`, reading by risk and reproducing each candidate against the real store and adapters | 7 new findings (cap reached) | **R1** (high): a held presence re-offered every poll cycle until retention → will-fix `8f52e5c`. **R2** (medium): the dedup key collapsed two labels in one second and close → reopen → close → will-fix `b7fc7ef`. **R3** (medium): one `commit-undelivered` wedged the client until restart → will-fix `6845969`. **R4** (medium): an actor registration never routed held events (R2.2) → will-fix `9503c8b`. **R5** (low): a lost wake-up between an empty read and the wait → will-fix `185032d`. **R6** (low): `/commit` and claims skipped the peer lease → will-fix `ab0bdfa` (+ `ebd8b2b` aligning three tests). **R7** (low): store and log paths not confined to `state.root` as the design says → will-fix `a43acf5` | [round 2](https://github.com/MadaraUchiha-314/the-loop/pull/499#issuecomment-6271308149) |

**The rounds stopped at the cap (`selfReviewCount: 2`), not at zero findings.** Round 2 was
a fresh read and found what the implementing session's read did not; nothing in it
repeats round 1, so the diminishing-returns guard did not fire. Every finding of both
rounds is dispositioned on the PR before its commit, one finding per commit. After the
last fix the gateway suites pass (206) and the full CLI suite is green on `ebd8b2b`:
6353 passed (`cd cli && uv run python -m pytest -q`, `THE_LOOP_CLI_CONFIG` unset).
