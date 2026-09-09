---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#332"
phase: needs-review
status: in-progress
---

# Execution Log: a closed poll-only work item leaves the board by itself

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-09 | — | Tier 3 (`human-approves-pr`; below `humanSignOffMinTier: 4`): a second candidate set for a question the poller already asks, under a window and a cap; one optional ledger field; no config key, schema, grant or route. Brainstorming skipped: the ticket names the options and ranks them. No authorized `the-loop execute` reaches this cloud session, so the selection is recorded here and every phase is walked |
| requirements-definition | 2026-09-09 | | [`requirements.md`](requirements.md) — three requirements, four abuse cases |
| design | 2026-09-09 | | [`design.md`](design.md) — the schedule, the set, the question; [`decision-115`](../../decisions/decision-115.md) |
| test-planning | 2026-09-09 | | [`testing-plan.md`](testing-plan.md) — fourteen rows, six applicable |
| tasks-breakdown | 2026-09-09 | | [`tasks.md`](tasks.md) — four tasks |
| implementation | 2026-09-09 | | On `claude/github-issue-332-z3xktv` — tasks 1–3 |
| verification | 2026-09-09 | | [`evidence/verification.md`](evidence/verification.md) — rows T1, T3, T9, T11, T13; [`evidence/security-review.md`](evidence/security-review.md) — four abuse cases, four closed |
| needs-review | 2026-09-09 | | PR raised; awaiting the owner (tier 3: `human-approves-pr`) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#335](https://github.com/MadaraUchiha-314/the-loop/pull/335) | tasks 1–4: the whole work item | open |

## Progress entries

### 2026-09-09 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–4, red first (the fourteen new tests were run against the unchanged
  source and fail there — the red block in
  [`evidence/verification.md`](evidence/verification.md)). Two constants beside
  `_SEEN_COMMENTS_CAP`; `PollState.absent_since` / `note_closure_check` and the
  `closureCheckedAt` field; `PollSummary.ledger_checks` on `poll.cycle`;
  `_closure_candidates` became `_candidate_sets` (tracked, ledger-only), the question
  became `_ask_closure` shared by both sets, and `_ledger_candidates` puts the second
  set on its schedule — listed, stamped and not-yet-due records out, longest-absent
  first — under the cap; a non-closure dates the record. The docs (`state.md`,
  `concepts.md`), the capability doc's rule and history row, the two catalog
  descriptions, and decision-115.
- **Checkpoint/tests:** `make check` — see `evidence/verification.md`. Existing
  assertions changed: one (`test_a_poll_only_record_is_not_reconciled` pinned
  issue-329's R3.2 and is now the pair
  `test_a_poll_only_record_seen_this_window_is_not_asked` /
  `test_a_closed_ledger_only_item_is_forgotten_and_never_asked_again`).
- **Self-review:** three passes over the diff. Pass one: `_ledger_candidates` re-parsed
  the `now` string it had just been handed and asserted on the result — it now takes
  the datetime cutoff computed once by the caller; the due-list sort would have compared
  `WorkItemRef` objects on a (impossible) tie — sorted by key now; a string
  `tuple[...]` annotation where the module uses `typing` — `Tuple`. Confirmed the
  design's claim that a hot reload updates `config.interval_seconds` in place
  (`_maybe_reload`). Pass two: the integration scenario asserted the record's key set
  and tripped on `forget`'s documented `"poll": null` tombstone — the assertion now
  reads populated sections; the testing plan's trace named two tests as planned rather
  than as written — aligned. Pass three: nothing new. Observations, out of scope:
  `uv.lock` re-resolves on every `uv run` because the 13.7.1 bump did not update it
  (not committed here); the full suite still leaves a fixture record under
  `.the-loop/portable/` in the checkout (the pre-existing leak issue-331's log noted) —
  removed before committing, not fixed here. One more, fixed here because this PR's
  own CI would trip on it: `test_one_repository_with_issues_disabled_does_not_blind_the_others`
  (issue-315) asserted the session record right after waiting for the tmux spawn, and
  the dispatcher registers after it spawns, on its own thread — 3 of 20 runs failed on
  the unchanged source; the assertion now waits for the record as it waited for the
  spawn.
- **Next:** the owner's review.
- **Blockers:** none.

### 2026-09-09 — spec chain drafted

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** read `_reconcile_closures` / `_closure_candidates` / `_process_item`,
  `PollState` (`finalize`, `baseline_comments`, `forget`, `flush`), `PollSummary` and
  `poll_once` in `poller/poller.py`; `Dispatcher.handle`'s closed branch, `_tracks` and
  `_record_closure` in `webhook/dispatcher.py` (the branch runs inline, so the stamp
  precedes the poller's `forget`); the issue-329 spec chain and decision-113; the
  issue-315 re-probe constant. Confirmed the ticket's account: a poll-only record is
  never asked, so its closure is never recorded. Chose the ticket's first option and
  wrote the four artifacts and the decision.
- **Checkpoint/tests:** baseline — `test_poller.py` green (203).
- **Next:** task 1, red first.
- **Blockers:** none.

## Verification results

> Only when this work item declared `test-planning` away. It did not: results live in
> [`testing-plan.md`](testing-plan.md).

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
| — | — | — | see `testing-plan.md` |

## Design critic review

> Not selected for this work item.

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| | | | | |

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self (diff) | the-loop (this session) | new findings — a re-parse-and-assert, a tie-unsafe sort, a stray annotation style: fixed | this log |
| 2 | self (tests + docs) | the-loop (this session) | new findings — a tombstone-blind assertion in the scenario, two planned-vs-written test names in the plan: fixed | this log |
| 3 | self (diff) | the-loop (this session) | zero (converged) | this log |
| — | critic | — | unavailable — `reviews.critics` is empty in this repository's config; does not count toward `criticReviewCount` | — |
| 4 | security | the-loop checklist | pass — four abuse cases, four closed | [`evidence/security-review.md`](evidence/security-review.md) |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no security-review
  skill is invocable from this session's plugin set)
- **Outcome:** pass — [`evidence/security-review.md`](evidence/security-review.md)
- **Human sign-off:** n/a (tier 3, below `security.review.humanSignOffMinTier: 4`)

## Final validation evidence

| Requirement | Proof |
|-------------|-------|
| R1.1, R1.2 | `test_a_closed_ledger_only_item_is_forgotten_and_never_asked_again`, `test_a_poll_only_record_seen_this_window_is_not_asked`, `test_a_poll_only_record_checked_this_window_is_not_asked`, `test_a_poll_only_record_with_an_unparsable_timestamp_is_due`, `test_a_listed_poll_only_record_is_not_asked`, `test_a_stamped_poll_only_record_is_not_asked` |
| R1.3, R1.7 | `test_ledger_only_records_are_asked_longest_absent_first_up_to_the_cap`, `test_unowned_and_degraded_ledger_only_records_do_not_spend_the_cap`; the issue-159 / issue-315 reconciliation tests unchanged |
| R1.4 | `test_a_closed_ledger_only_item_is_stamped_after_the_window` (stamped `ended`, `source: poll`, ledger forgotten, record kept) |
| R1.5 | `test_a_still_open_ledger_only_item_is_dated_not_closed`, `test_an_unanswerable_ledger_only_item_is_dated_not_retried_next_cycle`, `test_poll_state_absent_since_is_the_later_timestamp`, `test_poll_state_note_closure_check_writes_through` |
| R1.6 | `test_the_cycle_counts_ledger_checks` |
| R2.1–R2.3 | `test_a_poll_only_record_beside_a_session_record_is_tracked_not_ledger_only`, `test_a_record_with_poll_beside_another_section_is_asked_without_a_window` ×3; every issue-329 reconciliation test unchanged and green |
| R3.1–R3.3 | `docs/cli/state.md`, `docs/cli/concepts.md`, `docs/capabilities/webhook-triggers.md`, `decision-115`, the two catalog entries (`test_eventlog.py`, `make lint`) |
| A1–A4 | `evidence/security-review.md` |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`webhook-triggers.md`](../../capabilities/webhook-triggers.md) | the issue-329 reconciliation bullet no longer says a `poll`-only record is not asked; a new bullet states the lazy rule — the window on the ledger's two stamps, the cap, longest-absent first, the unchanged close path on a closure, the date-only write on a non-closure, `ledger_checks` | `issue-332` row added at the top |
| [`control-plane.md`](../../capabilities/control-plane.md) | unchanged — the board renders the record a closure leaves (`ended` only) exactly as issue-329 taught it; no new element, group or rule | none |
| [`cli.md`](../../capabilities/cli.md) | unchanged — no command, option or host behaviour changed | none |

## Documentation

| Document | What changed |
|----------|--------------|
| [`docs/cli/state.md`](../../cli/state.md) | the `poll` table gains `closureCheckedAt`; a paragraph on the lazy rule for a `poll`-only record; the delete note says what removing the date does |
| [`docs/cli/concepts.md`](../../cli/concepts.md) | *How a session ends*: one sentence on the item the poller only ever listed |
| [`docs/decisions/decision-115.md`](../../decisions/decision-115.md) + index row | time on the ledger rather than a counter; a constant window and cap rather than a key; the unanswerable case deferred |
| `README.md`, `skills/the-loop/**`, `docs/config/cli/polling-options.md` | unchanged — none describes closure reconciliation, and no option was added (the window and cap are constants, decision-115 D4) |
