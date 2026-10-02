---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#452"
---

<!-- Authored per the the-loop:writing skill. -->

# Self-review (issue-452)

> The self review before human review
> ([`reference/reviewing.md`](../../../../skills/the-loop/reference/reviewing.md)). I read
> the branch diff adversarially, asking which close path could still lose the record,
> which `check` could answer from the archive when live state exists, and what a
> reviewer would reject.

## Review cycles

### Cycle 1: every path that removes a checkout

1. **Checked: the normal close.** `_close_ended_session` reads before `close_session`,
   which is the only place `_cleanup_workspace` runs on a closure; the automatic
   `cleanup_work_item` after it finds the stamp already carrying the record.
2. **Checked: `keepCheckoutOnClose: true`.** The checkout survives the closure, so the
   closure's own read succeeds; a later explicit `cleanup` finds a record and skips the
   backfill.
3. **Checked: a session-less tracked closure** reads the registry's checkout when it is
   still a directory, and stamps without a record otherwise.
4. **Found and fixed: test doubles of the graph link lacked the new method.** The first
   full run failed `test_finish_grace.py`. An embedder's coupling can predate the method
   too, so the dispatcher treats a link without it as having no record, rather than the
   tests being changed to suit.
5. **Missed here, caught by the critic:** the second-delivery wipe and the hold path
   (`critic-review.md` #1, #2). Both fixed with tests.

### Cycle 2: `check` answering from the archive

1. **Checked: live state wins.** The archive is consulted only when `stateFound` is
   false, never for an inner loop (`--pr`), never for a bare id, and not under
   `--recompute` when the spec directory exists.
2. **Checked: the control-plane poll.** `graph_check` for an active session either finds
   its state or the item has no stamp (a reopen clears it), so dashboards are unchanged;
   the issue-238 `repoResolved: false` answer is untouched.
3. **Checked: exit codes.** An archived report has no nodes, so `--fail-on block` exits 0;
   `ok` is set from the outcome, so `--fail-on unmet` exits 0 only for `completed`.
4. **Checked: no new finding** after the critic's fixes; full suite, ruff, pyright and
   markdownlint clean.

## Outcome

Zero open findings.
