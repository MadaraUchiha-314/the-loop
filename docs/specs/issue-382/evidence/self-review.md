---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#382"
---

<!-- Authored per the the-loop:writing skill. -->

# Self-review: the poll clocks are this machine's, not the repository's

> The `self-review` node's record: the diff re-read adversarially against the design,
> before any other reviewer sees it.

## What I went looking for

| # | Question | Answer |
|---|---|---|
| 1 | Can a ref's clock and its ledger disagree in a way that loses a comment? | No. The ledger is the only thing that says what was seen; the clock only says *when to ask the provider a question*. The write order makes the failure direction explicit: clocks first, so a crash leaves the clock ahead of the body, and re-reading comment ids is what the ledger is already idempotent about |
| 2 | Does a stray clock — one whose `poll` section is gone — make an item read as *known*? | It did in the first draft: `_read` built a ledger out of the clocks alone, and `is_known` answers on `_items`, so a reset item with a surviving clock would have had its whole thread **forwarded** instead of baselined. `_read` now returns nothing when there is no section, and `test_a_stray_clock_does_not_make_a_cleared_item_known` pins it |
| 3 | Does the "write only when it changed" rule ever skip a write that mattered? | The comparison is against the exact clock-free body that was last read from or written to disk, so it skips only a byte-identical write. `data is None` (a `forget`) bypasses it entirely, and a ref never read from disk has no entry, so its first write always happens |
| 4 | Does the first cycle after a baseline still rewrite the record? | Yes, once: `finalize` adds `gaveUp: {}` to a ledger that had no give-up record. That is a real (if empty) ledger change, and normalising it away would be a behaviour change outside this work item. From the second full cycle on, a quiet item writes nothing — which is what the churn test asserts and what the dogfood measured |
| 5 | Is the upgrade fallback reachable more than once per record? | Only until the first write of that ledger, which strips the keys. A record nothing ever writes again keeps its stale clocks and keeps being read from them — correct, because nothing else knows when it was polled |
| 6 | Can the control plane serve a clock for a record that has none of its own? | No: `_with_clocks` merges into **existing** section dicts only, so a lingering clock cannot invent a `poll` section (`test_a_clock_never_invents_a_section`) |
| 7 | Is the in-memory clock cache a staleness bug anywhere? | The poller holds one for the process, which is correct — it is the only writer, under the single-instance lock. `core.workitems` and `reset` build one per call, so an API read never serves a cached map. The one race left is a reset running while a poller cycles, which the design's error table names: the item is first-sight either way and its next `finalize` re-dates it |
| 8 | Does anything still read a clock out of the record? | `grep -rn "lastPolledAt\|closureCheckedAt" cli/the_loop ui/src` after the change: the poller (in memory), the clock store itself, the two declarations in `state.py`, `core.workitems`' join, `core.attention`'s comparison (against the served record, so the joined value) and the dashboard's `lastActivity` (through the API). No reader was left on the old path |
| 9 | Is the classification test satisfied by construction or by coincidence? | By construction: S1 failed on the unclassified `StateLayout.poll_clocks` before the `GENERATED_PATHS` entry was written, and S3 failed again until `docs/cli/state.md` carried the same verdict. S5 evaluates the published `.gitignore` block against the new path — `.the-loop/local/` already covers it, and the test proves that rather than assuming it |

## What I changed after re-reading

- **`_read` no longer builds a ledger from clocks alone** (finding 2), with the test that
  would have caught it.
- **The `GENERATED_PATHS` entry for the work-item record** still listed `lastPolledAt`
  among what it holds. It now says what the record holds and, explicitly, what it does
  not.
- **`core/attention.py`'s comment** explained the clean-poll rule in terms of "the
  record's `poll.lastPolledAt`". The value now arrives through the join, and the comment
  says so — the rule itself is unchanged, and it still compares two things this machine
  wrote.
- **The issue-332 suites read a helper that joins both files** rather than asserting on
  the record. They are about the schedule, not the storage; asserting the storage there
  would have made the split look like a behaviour change in the diff.

## Round 2 — zero new findings

A second pass over the final diff, after the docs were written: every production change is
covered by a row of the testing plan, every moved sentence in `docs/cli/state.md` names
issue-382, and the three claims a reviewer is most likely to doubt — the record keeps no
clock, an upgraded record keeps its schedule, a quiet cycle writes nothing — each have a
test whose failure would be unambiguous. Converged.
