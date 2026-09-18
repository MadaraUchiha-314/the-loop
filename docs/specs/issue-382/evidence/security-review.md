---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#382"
---

<!-- Authored per the the-loop:writing skill. -->

# Security review: the poll clocks are this machine's, not the repository's

> The `security-review` node's record, against `requirements.md` § Security considerations
> and `design.md` § Security design. See `skills/the-loop/reference/security.md`.

## Security review (gate)

- **Mechanism:** the-loop checklist (`reference/security.md`), applied to the diff.
- **Outcome:** pass. No new attack surface; one existing surface is **removed**.
- **Human sign-off:** n/a (risk tier 3 — below the tier-4 threshold).

## The boundary this work item touches

One: **what the poller's closure schedule reads to decide whether to ask the provider
about an item.** Before this change that input sat in `portable/<slug>.json`, a file
tracked in git — so on a deployment whose `state.root` is a repository, anyone who could
open a pull request could propose a value for it. Issue-332's own review had to argue that
case (its A2). After the change the schedule reads a machine-local file that no pull
request can touch.

Nothing else moves. Both values are `_utcnow()` strings minted by the-loop; no comment
body, ticket field or webhook payload can reach either, and neither is an authority — no
path reads a clock to decide whether an item is armed, who may command it, or whether it
has ended.

## Abuse cases, and where each is closed

| # | Abuse case | Closed by | Asserted in |
|---|---|---|---|
| 1 | A clock is forged into the future to keep an item off the closure schedule | the schedule's only reaction to a future stamp is *not due*: the item stays a plain row, and no path writes `ended` from a timestamp. Forging now also requires write access to the operator's machine | `test_poller.py::test_a_poll_only_record_with_a_future_timestamp_is_not_asked` (unchanged, now reading the local clock), `test_pollclocks.py::test_a_future_clock_is_kept_verbatim_for_the_schedule_to_judge` |
| 2 | The clock file is mangled — a list, a number, a non-mapping entry, or not JSON at all — to crash a poll cycle or to fabricate a date | every read is best-effort and per entry: a bad value is dropped, a bad file is an empty map, and "no clock" means *due now* — one question, then a well-formed date | `test_pollclocks.py::test_a_malformed_file_reads_as_no_clock`, `::test_a_malformed_clock_reads_as_no_clock`, `test_poller.py::test_a_missing_clock_file_reads_as_due_now` |
| 3 | The clock file cannot be written (a full or read-only disk) and a delivery fails with it | the write logs at `warning` and returns; the in-memory map still answers, so the cycle stays consistent with itself | `test_pollclocks.py::test_an_unwritable_file_never_raises` |
| 4 | A stray clock is planted for a work item whose ledger was reset, to make the poller treat a fresh thread as already seen | a clock is a ledger's date, never a ledger: `_read` returns nothing for a ref with no `poll` section, so the item is first-sight and is baselined | `test_poller.py::test_a_stray_clock_does_not_make_a_cleared_item_known` |

## What the change removes

- **A tracked, proposable input to a background schedule.** See above.
- **Two timestamps per work item from every repository that tracks `state.root`.** They
  leaked nothing sensitive, but they were a per-minute record of when an operator's daemon
  was running, published in whatever repository holds the state — now it is local.

## Fail-closed

Not applicable in the deny sense: a missing clock grants nothing. The conservative
direction here is *ask the provider again*, which is what an absent or unparsable value
means, and it is bounded by the unchanged `LEDGER_CHECKS_PER_CYCLE` cap (twenty per
source per cycle).

## Secrets

None read, written, logged or moved. The file holds ISO-8601 timestamps keyed by
work-item ref — no token, no path, no conversation id — and the change takes two values
**out** of a tracked file.
