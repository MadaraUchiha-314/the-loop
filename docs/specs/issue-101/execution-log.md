---
type: execution-log
workItem: "issue-101"
phase: needs-review
status: in-progress
---

# Execution Log: one work item may be delivered by several PRs

> Append-only log of progress for the user's visibility. Checked in alongside
> the spec at `docs/specs/issue-101/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-25 |  | Issue #101 asks for an audit first ("check if it's already the case"). Audit → `requirements.md` Requirement 0: the event→work-item direction is already list-shaped (issue-93) and the poll path is already per-ref (issue-94); the **webhook close path** and the loop's own guidance are not. |
| design | 2026-07-25 |  | One payload-only predicate (`_closing_refs`) in the dispatcher; workspace/tmux behaviour follows from it. No config key, no new stored data, no API call. decision-039. |
| tasks-breakdown | 2026-07-25 |  | 10-task DAG (T1–T10) |
| implementation | 2026-07-25 |  | Implemented on `claude/github-issue-101-l8j95o` |
| needs-review | 2026-07-25 |  | PR opened with the reviewer briefing; `make check` green; awaiting human review (tier-3, `human-approves-pr`) |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| the-loop#102 | Whole work item — T1–T10 | open |

## Progress entries

### 2026-07-25 — audit + spec drafted

- **Phase:** requirements-definition → design → tasks-breakdown
- **Did:** Walked every site that relates a work item to a PR (router, session
  registry, poller core, GitHub poll provider, dispatcher, workspace cleanup,
  guidance docs, templates) and recorded the result as Requirement 0. Five of nine
  sites were already list-shaped — `linked_issue_numbers`/`extract_work_items` emit
  every linked issue (issue-93), the registry is per-ref, `_poll_provider` unions all
  of a listed item's refs, `_reconcile_closures` asks about the **session's own** ref,
  and `closure_event` carries `work_items=[ref]`. The gap is the webhook close branch
  in `Dispatcher.handle`, which closed *every* matched session on a `pull_request`
  `closed` event: the first PR of a series merging closed the linked issue's session,
  killed its tmux harness and deleted its checkout while the ticket was still open
  (`_cleanup_workspace` runs per closed session, so it inherited the same assumption).
  The existing test `test_dispatcher_auto_closes_session_on_pr_close` asserted exactly
  that behaviour, which is why it had never surfaced.
- **Design choice that shaped everything:** the webhook path is deliberately
  payload-only, and a PR-close payload cannot say whether the linked issue is still
  open — so the rule had to be decidable from the refs alone. "Only the object that
  closed ends" satisfies that, needs no config knob, and makes the lifecycle-close
  authz bypass strictly safer.
- **Checkpoint/tests:** none yet (spec phase).
- **Next:** implement T1–T10, TDD.
- **Blockers:** none. Tier 3 (`human-approves-pr`): spec + code approved together at
  the PR.

### 2026-07-25 — implemented (T1–T10)

- **Phase:** implementation → needs-review
- **Did:**
  - `webhook/dispatcher.py`: new `_closing_refs(routed)` — pure, payload-only,
    provider-agnostic; matches the number the payload's own `issue`/`pull_request`
    entity carries against `routed.work_items`. The close branch now skips a matched
    session whose ref is not in that set, logging it and emitting a new
    `session.kept_open` event. Nothing else in the branch moved (never spawn, never
    prompt, tmux + workspace per closed session).
  - `eventlog.py`: `session.kept_open` registered in `EVENT_TYPES` (the drift test
    enforces this; `the-loop events --types` documents it).
  - Tests, red before green (4 new/changed assertions failed against the old
    dispatcher, all pass after): `test_routing.py` — the linked issue's session stays
    active, a PR-ref session still closes, a second PR closing ends nothing, a
    malformed close payload closes nothing; `test_workspace.py` — the linked work
    item's worktree survives, the PR's own session still cleans up (the three existing
    cleanup tests re-pointed at the PR ref, which is the case they actually describe);
    `test_tmux_runner_integration.py` — a linked PR's close leaves the tmux session
    running even with `keepSessionOnClose: false`; integration —
    *the work item's session survives its first PR merging* (webhook) and *a merged PR
    does not close its still-open work item* (poll, guards the already-correct path
    against regression).
  - Guidance: execution-log template gained the **Pull requests** list;
    `work-on`/`execute-tasks` label and record every PR; `finish-tasks` verifies all of
    them and notes that closing the ticket is what ends the session;
    `reference/automation.md`, `docs/capabilities/webhook-triggers.md`,
    `docs/capabilities/spec-workflow.md` and `cli/README.md` carry the corrected end
    condition **and** the operational consequence (a PR merged without closing its
    ticket leaves the session active); `decision-039` + index.
- **Checkpoint/tests:** `make check` — ruff, `ruff format --check`, pyright,
  `scripts/validate_config.py`, `pytest` (463 tests) and markdownlint, all green.
  Red→green evidence recorded in the PR briefing.
- **Next:** human review of the PR (tier 3).
- **Blockers:** none.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop | Confirmed the poll path needed no change (reconciliation is registry- and ref-driven) and that `closure_event`'s `work_items=[ref]` keeps the polled close inside the new predicate; added the malformed-payload test after re-reading `_closing_refs` for its failure mode | this log |
| 2 | self | the-loop | Checked the fallout for narrowed `webhooks.ghWebhook.events` lists: dropping `issues` now leaks GitHub-ticketed sessions; the receiver's existing startup/hot-reload warning already names that omission, so no new warning was added — documented in decision-039 § Consequences | this log |
| 3 | self | the-loop | Re-read the three existing workspace/tmux close tests: they described "the work item's PR" but registered the session against the **issue**; re-pointed them at the PR ref (the case they actually assert) and added the linked-PR counterparts rather than deleting coverage | this log |

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; the change is a
  removal of an auto-close path with no new ingress, credential, command or parsed
  field).
- **Outcome:** pass — **strictly narrowing**. The lifecycle-close bypass of the
  authorized-actor guard (issue-94) now only ever ends the session for the object that
  closed, so a hostile `Closes #N` in a PR body can no longer end `#N`'s session
  (abuse case 1 of `requirements.md`). Close events are still never rendered into a
  harness prompt. The fail-closed direction is *keep state*: an unparseable close
  payload closes nothing.
- **Human sign-off:** n/a — risk tier 3, below `security.review.humanSignOffMinTier` (4).

## Final validation evidence

- **Red→green:** with the dispatcher change stashed, the new assertions fail
  (`test_pr_close_leaves_the_linked_issues_session_active`,
  `test_a_second_pr_closing_ends_nothing_while_the_work_item_is_open`,
  `test_a_malformed_close_payload_closes_nothing`,
  `test_dispatcher_pr_close_keeps_the_linked_work_items_worktree`); with it applied the
  whole suite passes.
- **AC coverage:** AC1 (unit + webhook/poll integration), AC2 (existing issue-close
  tests, unchanged), AC3 (`calls() == []` on the close), AC4 (PR-as-work-item close),
  AC5 (`session.kept_open` in `EVENT_TYPES` + the drift test), AC6/AC7 (workspace
  tests), AC8–AC10 (templates, commands, capability docs, references, decision-039).
- **Gates:** `make check` green (see the progress entry above).
