---
type: testing-plan
phase: test-planning
workItem: "issue-332"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: a closed poll-only work item leaves the board by itself

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (service) | yes | `PollState.absent_since` (the later timestamp; `""` for none or unparsable) and `note_closure_check` (written through at once); `_ledger_candidates` (a poll-only record absent for the window is asked once; one seen this window is not; one dated by a check this window is not; a listed one, a stamped one, one beside a session record, one beside `control` / `graph` / `collaborators` are not in the set; an unparsable timestamp is due; longest-absent first; the cap admits twenty and leaves the rest); the outcomes (still open → `closureCheckedAt` written, no close; `ProviderError` → `closureCheckedAt` written, error recorded; closed → `poll.closure_detected`, the close event, `poll` forgotten, `closures` counted, and the record not asked again); the counter on the summary and on `poll.cycle`; the unowned and degraded skips do not consume the cap; the tracked set is asked with no window and no cap | `uv run --project cli python -m pytest -q cli/tests/test_poller.py -k "ledger or poll_only or closure_check or absent_since"` |
| T2 | Unit (dashboard) | n/a — no dashboard change: the record a closure leaves behind (`ended` only) is the shape issue-329 already renders | | |
| T3 | Integration (scenario) | yes | through `poll_once` and the `gh` double: a labelled issue by an unlisted author is listed once (a poll-only record, no session), leaves the listing, is asked once after the window and dated as still open, is not asked again inside the window, and once closed upstream and due again is stamped `ended`, source `poll`, with its ledger forgotten | `uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py -k ledger` |
| T4 | Contract (OpenAPI / GraphQL SDL) | n/a — no route changes | | |
| T5 | End-to-end | n/a — the poller and the dispatcher's close path are exercised together by T3 over the real `Dispatcher` | | |
| T6 | UI / visual | n/a — no new element | | |
| T7 | Snapshot | n/a — assertions on record contents, events and counters | | |
| T8 | Performance / load | n/a — the bound is the design: at most twenty questions per provider per cycle, one per record per window; T1 asserts the cap and the window rather than timing them | | |
| T9 | Security / abuse case | yes | one negative test per abuse case A1–A4 (`requirements.md` § Security considerations) | `uv run --project cli python -m pytest -q cli/tests/test_poller.py cli/tests/test_poller_integration.py -k "ledger or poll_only or closure_check or absent_since"` |
| T10 | Accessibility | n/a — no new element | | |
| T11 | Migration / upgrade | yes | a ledger without `closureCheckedAt` (every 13.7.1 record) is due once `lastPolledAt` is a window old, and otherwise not; `poll.cycle` without the counter is byte-identical to today's; both event descriptions are in the catalog | `uv run --project cli python -m pytest -q cli/tests/test_eventlog.py cli/tests/test_docs_parity.py` |
| T12 | Manual exploratory | n/a — no GitHub deployment is reachable from this session; the reviewer's walk-through is the PR briefing's "what to check" | | |
| T13 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T14 | Security review (gate) | yes | the-loop checklist against A1–A4, recorded as evidence; tier 3 needs no human sign-off (`humanSignOffMinTier: 4`) | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.2, R1.5 | `test_poller.py::test_poll_state_absent_since_is_the_later_timestamp`, `test_poll_state_note_closure_check_writes_through` |
| T1 | R1.1, R1.2 | `test_a_closed_ledger_only_item_is_forgotten_and_never_asked_again`, `test_a_poll_only_record_seen_this_window_is_not_asked`, `test_a_poll_only_record_checked_this_window_is_not_asked`, `test_a_poll_only_record_with_an_unparsable_timestamp_is_due` |
| T1 | R1.1, R2.3 | `test_a_listed_poll_only_record_is_not_asked`, `test_a_stamped_poll_only_record_is_not_asked`, `test_a_poll_only_record_beside_a_session_record_is_tracked_not_ledger_only`, `test_a_record_with_poll_beside_another_section_is_asked_without_a_window` |
| T1 | R1.3, R1.7 | `test_ledger_only_records_are_asked_longest_absent_first_up_to_the_cap`, `test_unowned_and_degraded_ledger_only_records_do_not_spend_the_cap` |
| T1 | R1.4 | `test_a_closed_ledger_only_item_is_forgotten_and_never_asked_again` (the unit double stamps nothing; the stamp is T3's assertion) |
| T1 | R1.5 | `test_a_still_open_ledger_only_item_is_dated_not_closed`, `test_an_unanswerable_ledger_only_item_is_dated_not_retried_next_cycle` |
| T1 | R1.6 | `test_the_cycle_counts_ledger_checks` |
| T1 | R1.7, R2.1, R2.2 | the existing issue-94 / issue-159 / issue-315 / issue-329 reconciliation tests, unchanged and green (`test_a_poll_only_record_is_not_reconciled` is the one rewritten, into the pair R2.2 names) |
| T3 | R1.1–R1.5 | `test_poller_integration.py::test_a_closed_ledger_only_item_is_stamped_after_the_window` |
| T9 | A1 | `test_ledger_only_records_are_asked_longest_absent_first_up_to_the_cap`, `test_an_unanswerable_ledger_only_item_is_dated_not_retried_next_cycle` |
| T9 | A2 | `test_a_poll_only_record_with_a_future_timestamp_is_not_asked` |
| T9 | A3 | `test_a_still_open_ledger_only_item_is_dated_not_closed` |
| T9 | A4 | `test_a_closed_ledger_only_item_is_stamped_after_the_window` (the record carries `ended`, not nothing) |
| T11 | R1.6, R3.3 | `test_eventlog.py::test_every_emitted_event_type_is_documented`, `test_docs_parity.py` |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. GitHub is faked at its injection points (`FakeProvider`,
  the `gh` runner double).
- **Fixtures & data:** temp directories per test; timestamps written directly into the
  ledger (`2020-…` for *absent for the window*, `_utcnow()` for *seen this window*).
- **Credentials:** none.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T3, T9, T11, T13 | command, counts, duration, raw tail of the output; red → green per task | `verification.md` |
| T14 | the abuse-case table with verdicts and the tests that close each | `security-review.md` |

## Verification activities

- [x] T1 — the poller unit selection
- [x] T3 — the integration scenario
- [x] T9 — the abuse-case selection
- [x] T11 — `test_eventlog.py`, `test_docs_parity.py`
- [x] T13 — `make check`
- [x] T14 — `evidence/security-review.md`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_poller.py -k "ledger or poll_only or closure_check or absent_since"` | pass — 21 passed (17 new, one rewritten; the selection also matches four pre-existing ledger tests) | [`evidence/verification.md`](evidence/verification.md) |
| T3 | `uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py -k ledger` | pass — 3 passed (1 new scenario, red first) | [`evidence/verification.md`](evidence/verification.md) |
| T9 | `… -k "ledger or poll_only or closure_check or absent_since"` over both files | pass — 24 passed (A1–A4) | [`evidence/verification.md`](evidence/verification.md), [`evidence/security-review.md`](evidence/security-review.md) |
| T11 | `uv run --project cli python -m pytest -q cli/tests/test_eventlog.py cli/tests/test_docs_parity.py` | pass — 19 passed | [`evidence/verification.md`](evidence/verification.md) |
| T13 | `make check` | pass — see the evidence for the counts | [`evidence/verification.md`](evidence/verification.md) |
| T14 | the-loop checklist over A1–A4 | pass; no human sign-off at tier 3 | [`evidence/security-review.md`](evidence/security-review.md) |

**Not executed:** none.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
