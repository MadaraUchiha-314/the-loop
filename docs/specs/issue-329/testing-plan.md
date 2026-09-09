---
type: testing-plan
phase: test-planning
workItem: "issue-329"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: a closed work item is recorded as ended, and the board stops asking for a human on it

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (service) | yes | the store (`ENDED` in `SECTIONS`, a record with only `ended` is kept and indexed, `record_ended` / `ended` / `clear_ended`, a malformed stamp reads as not ended); the dispatcher's closed branch (a matched session's ref is stamped, a session-less tracked ref is stamped and disarmed, an untracked ref gains no record, the stamp names state/kind/reason/source/actor, `reopened` clears the stamp and emits); the poller (a paused session, a closed session and an armed record are reconciled once and not again once stamped, a poll-only record is not, a listed item clears its stamp, the failed / interrupted / degraded / unowned rules hold); the provider (`closed_by` → `Closure.actor` → `sender`, no `sender` without an actor); reset clears `ended`; the attention surface skips `awaiting-input` and `armed-without-session` for an ended record | `uv run --project cli python -m pytest -q cli/tests/test_workitem.py cli/tests/test_portable_index.py cli/tests/test_control.py cli/tests/test_routing.py cli/tests/test_poller.py cli/tests/test_reset.py cli/tests/test_core_attention.py` |
| T2 | Unit (dashboard) | yes | `buildWorkItemViews` carries `ended` and nulls `question` / `parked` for it; `itemGroup` never answers needs-you for an ended view (blocked rail, PR question, PR gate); `sidebarGroup` shipped for merged / issue-closed, idle for pr-closed; `rowFlag` `merged` / `closed`, not urgent; `attentionEntries` empty for an ended view; a record without the field is unchanged; the demo's ended item lands under Shipped | `cd ui && bun run test` |
| T3 | Integration (scenario) | yes | through the webhook receiver: an `issues closed` for a tracked item with no session stamps the record; a `reopened` clears it; through `poll_once`: a paused session's closed item is detected, stamped and its `poll` forgotten; a polled closure by an authorized closer runs cleanup, by an unlisted one defers `unauthorized-actor` | `uv run --project cli python -m pytest -q cli/tests/test_webhook_routing_integration.py cli/tests/test_poller_integration.py` |
| T4 | Contract (OpenAPI / GraphQL SDL) | n/a — `/work-items` and `/attention` are typed `additionalProperties: true`; no route changes | | |
| T5 | End-to-end | n/a — the close path, the poller and the dashboard join are each exercised by their own suites over the same record shape | | |
| T6 | UI / visual | n/a — no new element; the existing groups, dot, chip slot and banners take the ended state, asserted by T2 on the model that drives them | | |
| T7 | Snapshot | n/a — assertions on record contents, events and view fields | | |
| T8 | Performance / load | n/a — the widened candidate set costs one provider call per open, unlabelled tracked item per cycle after the first stamp (design §3.1); no new loop, no new listing | | |
| T9 | Security / abuse case | yes | one negative test per abuse case A1–A6 (`requirements.md` § Security considerations) | `uv run --project cli python -m pytest -q cli/tests/test_routing.py cli/tests/test_poller.py cli/tests/test_core_attention.py -k "ended or reopened or closer or untracked"` |
| T10 | Accessibility | n/a — no new element | | |
| T11 | Migration / upgrade | yes | a record without `ended` behaves exactly as at 13.6.0 on both surfaces (T1, T2 rows); the closure event without an actor is byte-identical to today's (T1); both new event types are in the catalog | `uv run --project cli python -m pytest -q cli/tests/test_eventlog.py cli/tests/test_docs_parity.py` |
| T12 | Manual exploratory | n/a — no GitHub deployment is reachable from this session; the reviewer's walk-through is the PR briefing's "what to check" | | |
| T13 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them, plus the dashboard's three | `make check` · `cd ui && bun run lint && bun run test && bun run build` |
| T14 | Security review (gate) | yes | the-loop checklist against A1–A6, recorded as evidence; tier 3 needs no human sign-off (`humanSignOffMinTier: 4`) | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.4 | `test_workitem.py::test_a_record_with_only_ended_is_kept_and_indexed`, `test_portable_index.py` (sections lists `ended`) |
| T1 | R1.1, R1.6 | `test_control.py::test_record_ended_and_clear_ended`, `test_a_malformed_ended_reads_as_not_ended` |
| T1 | R1.1–R1.3, R1.6 | `test_routing.py::test_an_issue_close_stamps_the_work_item_ended`, `test_a_close_with_no_session_still_stamps_a_tracked_record`, `test_a_close_for_an_untracked_ref_creates_no_record`, `test_a_pr_merge_stamps_the_prs_own_record_and_not_the_linked_issue`, `test_a_closed_session_record_counts_as_tracked` |
| T1 | R2.1, R2.3 | `test_routing.py::test_a_reopen_clears_the_ended_stamp`, `test_a_reopen_without_a_stamp_writes_nothing` |
| T1 | R3.1–R3.4 | `test_poller.py::test_a_paused_sessions_closed_item_is_reconciled`, `test_a_record_without_a_session_is_reconciled[control / graph / collaborators]`, `test_a_closed_session_is_asked_once_and_not_again_once_stamped`, `test_a_live_session_beside_a_stamp_is_still_reconciled`, `test_a_poll_only_record_is_not_reconciled`, the existing failed/interrupted/degraded/unowned tests |
| T1 | R2.2 | `test_poller.py::test_a_listed_item_clears_its_ended_stamp` |
| T1 | R4.1, R4.2 | `test_poller.py::test_provider_closure_carries_the_closer`, `test_provider_closure_event_names_the_closer_as_sender` (both halves: with and without a closer) |
| T1 | R1.5 | `test_reset.py::test_reset_clears_the_ended_section` |
| T1 | R5.4 | `test_core_attention.py::test_an_ended_item_asks_for_no_attention` |
| T2 | R5.1–R5.3, R5.5 | `model.test.ts › ended`, `grouping.test.ts › sidebarGroup (ended)`, `rowFlag`, `attentionEntries` |
| T3 | R1.3, R2.1 | `Scenario: A closed issue with no session is stamped ended`, `Scenario: Reopening an issue clears the stamp` |
| T3 | R3.1, R4.3 | `Scenario: A paused session's closed item is detected by the poller`, `Scenario: A polled closure by an authorized closer releases the item`, `Scenario: A polled closure by an unlisted closer is deferred` |
| T9 | A1–A6 | the negative tests named in `evidence/security-review.md` |
| T11 | R1.6, R6 | event catalog, docs parity |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. GitHub is faked at its injection points (`FakeProvider`,
  the `gh` runner double, the webhook receiver's `server_factory` with `FakeTmux`).
- **Fixtures & data:** temp directories per test.
- **Credentials:** none.
- **Bring-up:** `uv sync` · `cd ui && bun install --frozen-lockfile` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T3, T9, T11, T13 | command, counts, duration, raw tail of the output; red → green per task | `verification.md` |
| T14 | the abuse-case table with verdicts and the tests that close each | `security-review.md` |

## Verification activities

- [x] T1 — the service unit suites named above
- [x] T2 — `cd ui && bun run test`
- [x] T3 — the two integration suites
- [x] T9 — the abuse-case selection
- [x] T11 — `test_eventlog.py`, `test_docs_parity.py`
- [x] T13 — `make check` · `cd ui && bun run lint && bun run test && bun run build`
- [x] T14 — `evidence/security-review.md`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_workitem.py cli/tests/test_portable_index.py cli/tests/test_control.py cli/tests/test_routing.py cli/tests/test_poller.py cli/tests/test_reset.py cli/tests/test_core_attention.py` | pass — 496 passed (22 new; one rewritten) | [`evidence/verification.md`](evidence/verification.md) |
| T2 | `cd ui && bun run test` | pass — 219 passed (7 new) | [`evidence/verification.md`](evidence/verification.md) |
| T3 | `uv run --project cli python -m pytest -q cli/tests/test_webhook_routing_integration.py cli/tests/test_poller_integration.py` | pass — 63 passed (5 new scenarios, red first) | [`evidence/verification.md`](evidence/verification.md) |
| T9 | `… -k "ended or reopened or closer or untracked"` | pass — 11 passed (A1–A6) | [`evidence/verification.md`](evidence/verification.md), [`evidence/security-review.md`](evidence/security-review.md) |
| T11 | `uv run --project cli python -m pytest -q cli/tests/test_eventlog.py cli/tests/test_docs_parity.py` | pass — 19 passed | [`evidence/verification.md`](evidence/verification.md) |
| T13 | `make check` · `cd ui && bun run lint && bun run test && bun run build` | pass — see the evidence for the counts | [`evidence/verification.md`](evidence/verification.md) |
| T14 | the-loop checklist over A1–A6 | pass; no human sign-off at tier 3 | [`evidence/security-review.md`](evidence/security-review.md) |

**Not executed:** none.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
