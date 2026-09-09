---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#329"
phase: needs-review
status: in-progress
---

# Execution Log: a closed work item is recorded as ended, and the board stops asking for a human on it

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-09 | — | Tier 3 (`human-approves-pr`; below `humanSignOffMinTier: 4`): one portable section, written on the shared close path, read by two attention surfaces; no new grant, route or sensitive path. Brainstorming skipped: the ticket's root-cause analysis and fix direction are the requirement. No authorized `the-loop execute` reaches this cloud session, so the selection is recorded here and every phase is walked |
| requirements-definition | 2026-09-09 | | [`requirements.md`](requirements.md) — six requirements, six abuse cases |
| design | 2026-09-09 | | [`design.md`](design.md) — the fact, the writer, more closures, the readers; [`decision-113`](../../decisions/decision-113.md) |
| test-planning | 2026-09-09 | | [`testing-plan.md`](testing-plan.md) — fourteen rows, eight applicable |
| tasks-breakdown | 2026-09-09 | | [`tasks.md`](tasks.md) — six tasks |
| implementation | 2026-09-09 | | On `claude/github-issue-329-fide3i` — tasks 1–5 |
| verification | 2026-09-09 | | [`evidence/verification.md`](evidence/verification.md) — rows T1, T2, T3, T9, T11, T13; [`evidence/security-review.md`](evidence/security-review.md) — six abuse cases, six closed |
| needs-review | 2026-09-09 | | PR raised; awaiting the owner (tier 3: `human-approves-pr`) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| | | |

## Progress entries

### 2026-09-09 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–6, red first (the 20 new service tests and the 7 dashboard tests
  were run against the unchanged source and fail there — the red block in
  [`evidence/verification.md`](evidence/verification.md)). `ENDED` as the fifth portable
  section with `record_ended` / `ended` / `clear_ended` on `ControlStore` (the stamp
  gets its `at` there); reset clears it; the dispatcher's closed branch stamps and
  disarms every closing ref the machine tracks — the matched session's, and any ref with
  a session record of any status or a portable record — and a `reopened` action clears
  the stamp; the poller reconciles every session record plus every armed, frozen or
  rostered portable record, skips a stamped record unless a live session sits beside
  it, and clears the stamp of any item it lists; `GhItemState.closed_by` →
  `Closure.actor` → the synthesized event's `sender`; the shared
  `POLL_CLOSURE_DELIVERY_PREFIX` on the router so the stamp can say which ingress saw
  the close; `core/attention.py` skips `awaiting-input` and `armed-without-session`
  for a stamped record; the dashboard's join carries `ended`, nulls the question and
  the gate, keeps the item out of `needs-you`, groups it Shipped/Idle with a muted chip
  and drops it from the inbox; the demo's shipped item carries the stamp; the docs.
- **Checkpoint/tests:** `make check` and the dashboard's three commands — see
  `evidence/verification.md`. Existing assertions changed: one
  (`test_an_already_closed_session_is_not_reconciled_again` inverted into
  `test_a_closed_session_is_asked_once_and_not_again_once_stamped`, because the rule
  it pinned was the gap). Three existing test files gained a tmp `portable_dir`
  (`test_routing.py`'s factory, `test_workspace.py`'s two): a close now writes a
  record, and `RoutingConfig`'s default directory is the checkout's own.
- **Self-review:** three passes over the diff. Pass one found a real gap — a stamp
  arriving through the tracked directory from another machine would have stopped this
  machine's poller from ever closing its still-live session; the skip now applies only
  when no live session sits beside the stamp, with a test — plus a side-effecting list
  comprehension on the close path (a plain loop now), a `ControlStore` rebuilt per
  candidate per cycle (cached), and `_closing_refs` recomputed per ref in the reopen
  path. Pass two found two doc gaps (the store's module docstring example; the cleanup
  table in `docs/cli/state.md`). Pass three found nothing new.
- **Next:** the owner's review.
- **Blockers:** none.

### 2026-09-09 — spec chain drafted

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** read the close path (`Dispatcher.handle`'s closed branch, `close_session`,
  `_cleanup_after_close`), the poller's `_reconcile_closures` and `_process_item`, the
  GitHub provider's `fetch_item_state` / `closure` / `closure_event`, the store
  (`WorkItemStore.write_section`, `SECTIONS`), `reset.py`, `cleanup.py`,
  `core/attention.py`, and the dashboard's `model.ts` / `grouping.ts` / `Sidebar.tsx`
  / `WorkItemDetail.tsx` at `cab21a6`; confirmed the ticket's five causes, and found
  a sixth fact that decides the fix direction — the closed **session** record keeps the
  row on the board whatever happens to the portable record, so deletion retires
  nothing. Wrote the four artifacts and the decision.
- **Checkpoint/tests:** baseline — `test_routing.py`, `test_poller.py`,
  `test_control.py`, `test_core_attention.py`, `test_workitem.py`, `test_reset.py`
  green; `cd ui && bun run test` green.
- **Next:** task 1 (the fact), red first.
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
| 1 | self (diff) | the-loop (this session) | new findings — a cross-machine stamp would strand a live session (fixed, tested); a side-effecting comprehension, an uncached store, a recomputed set: cleaned | this log |
| 2 | self (diff + docs) | the-loop (this session) | new findings — two doc gaps: fixed | this log |
| 3 | self (diff) | the-loop (this session) | zero (converged) | this log |
| — | critic | — | unavailable — `reviews.critics` is empty in this repository's config; does not count toward `criticReviewCount` | — |
| 4 | security | the-loop checklist | pass — six abuse cases, six closed | [`evidence/security-review.md`](evidence/security-review.md) |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no security-review
  skill is invocable from this session's plugin set)
- **Outcome:** pass — [`evidence/security-review.md`](evidence/security-review.md), six abuse cases closed
- **Human sign-off:** not required (tier 3 < `humanSignOffMinTier: 4`); the owner's PR approval is the gate

## Final validation evidence

| Requirement | Proof |
|-------------|-------|
| R1.1, R1.6 | `test_routing.py::test_an_issue_close_stamps_the_work_item_ended`, `test_the_stamp_is_logged_as_work_item_ended`; `test_control.py::test_record_ended_and_clear_ended` |
| R1.2 | `test_a_pr_merge_stamps_the_prs_own_record_and_not_the_linked_issue`, `test_a_close_for_an_untracked_ref_creates_no_record`, `test_a_closed_session_record_counts_as_tracked` |
| R1.3 | `test_a_close_with_no_session_still_stamps_a_tracked_record`; `Scenario: A closed issue with no session is stamped ended` |
| R1.4 | `test_workitem.py::test_a_record_with_only_ended_is_kept_and_indexed`; `graph` untouched by the close path (diff) |
| R1.5 | `test_reset.py::test_reset_clears_the_ended_section`; `cleanup.py` imports no store (existing assertion) |
| R2.1, R2.3 | `test_a_reopen_clears_the_ended_stamp`, `test_a_reopen_without_a_stamp_writes_nothing`; `Scenario: Reopening an issue clears the stamp` |
| R2.2 | `test_poller.py::test_a_listed_item_clears_its_ended_stamp` |
| R3.1 | `test_a_paused_sessions_closed_item_is_reconciled`, `test_a_record_without_a_session_is_reconciled[control / graph / collaborators]`, `test_a_closed_session_is_asked_once_and_not_again_once_stamped`, `test_a_live_session_beside_a_stamp_is_still_reconciled`; `Scenario: A paused session's closed item is detected by the poller` |
| R3.2 | `test_a_poll_only_record_is_not_reconciled` |
| R3.3, R3.4 | the existing issue-94 / issue-159 / issue-315 reconciliation tests, unchanged and green |
| R4.1, R4.2 | `test_provider_closure_carries_the_closer`, `test_provider_closure_event_names_the_closer_as_sender` |
| R4.3 | `Scenario: A polled closure by an authorized closer releases the item`, `Scenario: A polled closure by an unlisted closer is deferred` |
| R5.1–R5.3 | `model.test.ts › an ended work item (issue-329)` (four cases), `grouping.test.ts › sidebarGroup for an ended item` (three cases) |
| R5.4 | `test_core_attention.py::test_an_ended_item_asks_for_no_attention` |
| R5.5 | `grouping.test.ts › reads the demo's shipped item from its stamp`; `model.test.ts › treats a record without the field … as open` |
| R6.1, R6.2 | `docs/cli/state.md`, the two capability docs, `decision-113` (below); `make lint` (markdownlint) clean |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`docs/capabilities/webhook-triggers.md`](../../capabilities/webhook-triggers.md) | two behaviour bullets — the closure stamp (with or without a session; `reopened` clears it) and the widened reconciliation; the deferred-cleanup paragraph now says both ingresses name the closer | `issue-329` row added at the top |
| [`docs/capabilities/control-plane.md`](../../capabilities/control-plane.md) | the sidebar grouping bullet gains the ended rule; the `awaiting-input` bullet gains the service-side rule | `issue-329` row added at the top |
| [`docs/capabilities/cli.md`](../../capabilities/cli.md) | the issue-315 bullet's "that scope's sessions" became "that scope's tracked items", pointing at webhook-triggers | none (one clause) |

## Documentation

| Document | What changed |
|----------|--------------|
| [`docs/cli/state.md`](../../cli/state.md) | the record's section list; a new `ended` section (fields, when written, when cleared, what deleting it does); the index's `sections`; the reset and cleanup tables; the security paragraph's disclosure sentence |
| [`docs/decisions/decision-113.md`](../../decisions/decision-113.md) + index row | why the record is stamped and kept, why `graph` stays, why attribution rather than a relaxed gate |
| [`ui/README.md`](https://github.com/MadaraUchiha-314/the-loop/blob/main/ui/README.md) | the sidebar sentence names where an ended item goes |
| `README.md`, `skills/the-loop/**`, the docs site's other pages | unchanged — none of them describes closure or the board's groups |
