---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#538"
---

# Security review: pull-request session notices (issue-538)

## Security review (gate)

- **Mechanisms:** (1) the-loop checklist (`reference/security.md`), checked against
  `git diff origin/main -- cli/`. (2) The harness's built-in `/security-review`, run as a
  separate pass. **Its result is pending, and this record is updated with it before review
  is requested.**
- **Risk tier:** 3. No sensitive path is touched (no schema, `.the-loop/**`, workflow,
  auth, secret or credential path), so no named human security sign-off is required.
- **Checklist outcome:** pass, with no findings. The one security-relevant defect found in
  this PR's reviews, critic C1 (shared tmux paste buffers could deliver one conversation's
  text into another), is fixed in `f3885bf`.

| # | Item | Result | Evidence |
|---|------|--------|----------|
| 1 | Design boundaries enforced | pass | The one new boundary, daemon → work item's session (a paste), is enforced in `prnotice.render`, whose parameters are two parsed `WorkItemRef`s, a reason code looked up in `DECLINE_REASONS`, and identifiers filtered by `_identifier()`. Its two callers (`_notify_owner`, `_decline_into`) pass only `TmuxRunner.target_for` output, literal reason codes and compiled-graph node ids. |
| 2 | Untrusted input constrained at ingress | pass | No PR title, body, branch or comment is a parameter of anything new. The close path's refs come from `_closing_refs` (parsed numbers) and the registry. An unknown reason code renders `unspecified`, never the code. |
| 3 | Untrusted content cannot steer privileged behaviour | pass | A notice moves no pointer and writes no state. The outer pointer moves only through `Runtime.advance` on the outer node's own exit chain, and only when that node is parked on `await-inner-loops` (`on_inner_loop_finished`). A close without a merge triggers no re-evaluation. In a declined or failed spawn, the event keeps its existing untrusted-data framing; the notice sits ahead of it, outside that framing. |
| 4 | No secrets | pass | No credential is read, written or rendered. The new events carry refs, transition names, reason codes and error strings; `EventLog.emit` scrubs session-credential values as before. |
| 5 | Fails closed | pass | No record, no tmux target, or a closed record → `pr_notice_skipped(no-live-session)`. Paused → `skipped(paused)`. A paste failure or exception → `pr_notice_failed`, with no retry and no released delivery. Outer state unreadable or not parked → nothing re-evaluated (`not-parked`; `_guarded` returns `None` on fault). |
| 6 | Least privilege | pass | No new permission or network call. The paste goes only to the owning record's own tmux target. The background re-evaluation holds the same per-work-item state lock as every other writer. |
| 7 | Abuse cases have negative tests | pass | 1: `test_a_merged_pull_request_session_is_reported_to_the_work_item` (hostile title/body/branch absent) and `test_identifiers_are_filtered_and_bounded`. 2: `test_a_pull_request_closed_unmerged_is_reported_with_its_gate` (no re-evaluation) and `test_an_unparked_work_item_is_left_untouched` (state byte-identical). 3: `test_an_unlinked_pull_request_closing_tells_nobody`. 4: `test_a_redelivered_merge_is_reported_once`. Cross-conversation paste: `test_two_deliveries_never_share_a_paste_buffer`. |
| 8 | New dependencies | pass (n/a) | None. `uuid`, `threading` and `string` are stdlib. |

## Built-in `/security-review`

_Pending: appended when the pass returns._
