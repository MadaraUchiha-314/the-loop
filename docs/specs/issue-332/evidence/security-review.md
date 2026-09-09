# Security review — issue-332

> Mechanism: the-loop checklist (`security.review.mechanism: auto`; no security-review
> skill is invocable from this session's plugin set). Tier 3: below
> `security.review.humanSignOffMinTier: 4`, so no named human sign-off is required; the
> owner's PR approval is the gate.

## Threat model recap

The change adds a second candidate set to closure reconciliation — portable records
carrying only `poll`, with no session — under a window read from two timestamps the
poller itself writes and a cap per provider per cycle. Its only new write on a
non-closure is `poll.closureCheckedAt`; a closure is stamped by the dispatcher's existing
close path from the provider's answer, through the existing `_tracks` gate, and the
existing cleanup actor gate is untouched. The rule is a schedule for a question the
poller already asks; it arms nothing, spawns nothing and deletes nothing local.

## Abuse cases — disposition

| # | Abuse case | Closed by | Evidence |
|---|------------|-----------|----------|
| A1 | Many poll-only records are planted in a tracked `portable/` directory to make the poller spend provider calls, or a record that never answers is planted to hold the head of the queue | `LEDGER_CHECKS_PER_CYCLE` bounds the questions per provider per cycle; a *still open* **and** an unanswerable answer both write `closureCheckedAt`, so every record asked is deferred a full window and the queue drains | `test_poller.py::test_ledger_only_records_are_asked_longest_absent_first_up_to_the_cap` (twenty, then the remaining five), `test_an_unanswerable_ledger_only_item_is_dated_not_retried_next_cycle` |
| A2 | A record's `lastPolledAt` or `closureCheckedAt` is forged into the future to keep an item on the board, or to make the poller stamp it | a future stamp is simply not due — the item stays a plain row, which is 13.7.1's behaviour — and no path writes `ended` from a timestamp: only the provider's *closed* answer reaches the stamp | `test_poller.py::test_a_poll_only_record_with_a_future_timestamp_is_not_asked` (no question, no stamp) |
| A3 | The lazy check closes or hides an item on a *still open* or unanswerable answer | `_ask_closure` returns `False` for both; the ledger-only branch then writes a date and nothing else — no event to the dispatcher, no stamp, no forget | `test_poller.py::test_a_still_open_ledger_only_item_is_dated_not_closed` (no dispatched event, stamp `None`, ledger kept), `test_an_unanswerable_ledger_only_item_is_dated_not_retried_next_cycle` |
| A4 | A confirmed closure deletes the record instead of stamping it, so the closure fact is lost | the dispatcher's closed branch runs inline in `handle`: `_tracks` sees the `poll` section, `_record_closure` stamps `ended`, and only then does the poller's `forget` drop `poll` — the record ends as `ended` (plus the section tombstone), kept and indexed | `test_poller_integration.py::test_a_closed_ledger_only_item_is_stamped_after_the_window` (the record's one populated section is `ended`; `source: poll`, `actor: octocat`) |

## Checklist

- [x] AuthN/AuthZ unchanged: the cleanup gate (`_cleanup_after_close`), the router's
  actor guard and the `_tracks` gate are untouched; the new timestamp is consulted by
  no control, spawn or gate path (A3, A4).
- [x] Provenance: the only thing that can stamp a ledger-only record is the provider's
  own state answer, through the same synthesized event a tracked closure uses — never
  record contents, never comment text (A2, A4).
- [x] Input validation: the two timestamps are parsed against the one shape the poller
  writes; anything else reads as *unknown* (due), never raises, and is overwritten by a
  well-formed date after one question (`test_a_poll_only_record_with_an_unparsable_timestamp_is_due`).
- [x] Bounded cost: the cap per provider per cycle, one question per record per window,
  ownership and degraded scope as skips that do not spend the cap
  (`test_unowned_and_degraded_ledger_only_records_do_not_spend_the_cap`) (A1).
- [x] Secrets: nothing new is stored; `closureCheckedAt` is a timestamp; `poll.cycle`
  gains a count.
- [x] Fail closed, restated: no ledger-only record means 13.7.1 behaviour; reconciliation
  never runs on a failed, interrupted or degraded listing (existing tests unchanged and
  green); an unanswerable item is deferred, not closed; the tracked set keeps its rules
  (`test_a_record_with_poll_beside_another_section_is_asked_without_a_window`,
  `test_a_poll_only_record_beside_a_session_record_is_tracked_not_ledger_only`).
- [x] Disclosure: `docs/cli/state.md` documents the new field and the rule; the record
  discloses one more timestamp, nothing about a person.
- [x] Evidence redaction: every login, ref and path in the tests and evidence is a
  fixture (`octocat`, `nobody`, `octo/repo`, a pytest tmp path).

## Outcome

**Pass** on the autonomous checklist. No human sign-off required at tier 3; the pull
request's review is the human gate.
