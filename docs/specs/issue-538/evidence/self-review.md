---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#538"
---

# Self-review: tell the work item's session what happens to its pull-request sessions

> Policy (`the-loop critic policy`): `selfReviewCount: 2`, `stopOnNoNewFindings: true`.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | claude/claude-opus-5-5 (author session) | new findings | **F1** the close path runs inside `Dispatcher.handle`, before the receiver answers `202`, so a passing outer re-evaluation (a label call, an assignment paste, possibly an operator's `verify-tests` command) would hold the webhook → fixed: `_reevaluate_outer` runs it on a short-lived daemon thread; new scenario `test_a_slow_outer_reevaluation_does_not_hold_the_webhook` (red: timed out; green). Checked, no finding: a merged PR without a session of its own still triggers the re-run, which is right because the re-run needs the pointer parked on an `await-inner-loops` node; `completed` then `merged` sends two notices for two facts and the second re-run reports `not-parked`. | [PR #539 comment](https://github.com/MadaraUchiha-314/the-loop/pull/539#issuecomment-6989378354) |
| 2 | claude/claude-opus-5-5 (author session) | zero (converged) | Re-read the diff against R1–R4 and abuse cases 1–4. Both `prnotice.render` callers pass only parsed refs, literal reason codes, `TmuxRunner.target_for` output and compiled-graph node ids. Every notice path is wrapped so it cannot raise into its caller. `_decline_into` leaves `_deliver_into`'s release-for-redelivery unchanged. Exactly one `session.pr_notice_*` event per notice. A notice's tmux paste on the ingress thread is the same class of work as the `_close_tmux` call already there. No new findings. | this file |
