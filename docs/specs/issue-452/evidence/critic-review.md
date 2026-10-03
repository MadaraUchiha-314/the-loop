---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#452"
---

<!-- Authored per the the-loop:writing skill. -->

# Critic review (issue-452)

> One critic round, run by an independent reviewer agent in this work item's cloud
> session against the uncommitted diff (no `the-loop critic` harness is installed in
> this checkout). Every finding was reproduced or reasoned through, fixed with a
> regression test that is red on the first commit (`59fce06`) and green after, or
> recorded as out of scope.

## Round 1

| # | Severity | Finding | Disposition |
|---|----------|---------|-------------|
| 1 | major | A second delivery of the same closure (poller and webhook) re-stamped the item with the checkout already gone, replacing `terminal` with nothing and `completed` with `unknown`. Reproduced by the reviewer. | **Fixed.** `_record_closure` keeps the prior stamp's record when its own read finds none, and a prior `cancelled` stays cancelled. Test: `test_a_second_close_delivery_keeps_the_first_ones_record`. |
| 2 | minor | An operator's `sessions close`/`cleanup` during the issue-405 endgame hold removed the checkout before the sweeper stamped the closure, so the item most likely to be complete was stamped `unknown`. | **Fixed.** `close_session` and `cleanup_work_item` read the record onto the held `_PendingClose` before removing anything; the sweeper's stamp uses it. Test: `test_an_operator_close_during_the_endgame_hold_keeps_the_record`. |
| 3 | minor (security) | `completedAt` was copied unfiltered from the agent-writable state file and printed by `check`. | **Fixed.** Held to an ISO-8601 shape. Test: `test_abuse_forged_fields_are_filtered` now forges an OSC escape in `exitedAt`. |
| 4 | minor | A symlinked `evidence/` (`-> /`) was followed and the whole tree walked before the 50-name cap, on the close path. | **Fixed.** A symlinked or escaping `evidence/` is not listed; links inside are not followed; the walk stops after 1,000 entries. Tests: `test_abuse_a_symlinked_evidence_directory_is_not_walked`, `test_a_large_evidence_tree_is_walked_only_so_far`. |
| 5 | minor | Code that runs before `_guarded`'s `try` (or an injected coupling) could raise out of `_terminal_record`, before `close_session`. | **Fixed.** The dispatcher's read catches everything and returns `None`. Test: `test_a_coupling_that_raises_still_closes_and_stamps`. |
| 6 | minor | The cleanup backfill could resurrect a stamp a concurrent reopen cleared. | **Fixed.** Re-read and write under the portable store's lock (`WorkItemStore.lock()`), only if unchanged. Test: `test_cleanup_does_not_resurrect_a_stamp_a_reopen_cleared`. |
| n1 | nit | `state_reason: duplicate` read as closed-externally. | **Fixed.** A duplicate is a cancellation. Test: `test_a_duplicate_close_is_a_cancellation`. |
| n2 | nit | `_record_closure` re-read the checkout when the caller's read had already found nothing. | **Fixed.** An explicit "not read" sentinel: it reads only when nobody has. |
| n3 | nit | An item re-armed without being reopened keeps its stamp, so `check <ref>` elsewhere answers from the archive until the new session writes state. | **Out of scope**, recorded in `bugfix.md`: issue-329's rule is that only a reopen clears the stamp, and reopening is the supported way to resume. |

The reviewer confirmed as correct: the ordering on the normal close path and on the
sweeper's finish, reopen clearing, "a found state file wins", the bare-id exclusion and
the `--fail-on` semantics.

## Round 2

Not run: every round-1 finding was fixed with a test, and the second self-review cycle
(`self-review.md`) found nothing new.
