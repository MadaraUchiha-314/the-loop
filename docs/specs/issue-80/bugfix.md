---
type: bugfix
phase: requirements-definition
workItem: issue-80
status: draft
approvedBy: []
severity: high
collaborators: [engineer]
overrides: {}
---

# Bugfix spec: failed events are never retried — dead tmux sessions, and the poller baselining failures as "processed"

> Phase 1 of 3 for a bug (bugfix → design → tasks). Human approval for this
> tier-3 change happens at the PR (`autonomy.tiers."3": human-approves-pr`).

## Summary

Two linked defects mean an event the-loop **fails to process is silently
dropped**, never retried:

1. **Dead tmux session, no respawn (the issue title).** With
   `routing.runner: tmux`, the dispatcher delivers a routed event by
   bracketed-pasting into a work item's live harness TUI (tmux session
   `loop-<slug>`). When that session has crashed or been killed, delivery fails;
   the dispatcher only releases the delivery for retry, and nothing recreates
   the session — so every retry hits the same missing session.

2. **The poller marks failed events as "processed" (the issue comments).** The
   poller ends every cycle with
   `state.update(ref, [all current comment ids], now)`
   (`cli/the_loop/poller/poller.py`), which (a) baselines **every** comment as
   "seen" regardless of whether its dispatch succeeded, and (b) marks the work
   item "known", flipping `first_sight` false. So a comment (or spawn) whose
   dispatch failed is recorded as done and **never retried on the next poll** —
   exactly what the reporter observed: *"even though the spawn of the tmux
   failed, it didn't pick that up in the next poll … probably because it was
   marked as processed in some log file."*

There is no retry budget anywhere on the pull path, and no terminal "gave up"
signal. Tracked as
[issue #80](https://github.com/MadaraUchiha-314/the-loop/issues/80) and its
comments.

## Steps to reproduce

**Dead session (webhook or poll):** spawn a tmux-mode session for a work item,
`tmux kill-session -t loop-<slug>`, then route any event for it — delivery fails
forever into the missing session.

**Poller baseline bug:** run `the-loop poll start` with `routing.runner: tmux`
against a labelled issue. If the tmux spawn fails on the first cycle, the item is
recorded "known" and its comments baselined, so no later cycle retries the spawn
or the comment — the item is stuck with no session.

## Expected vs actual

- **Expected:** an event the-loop fails to process is **retried** on subsequent
  polls, up to a **configurable** number of attempts (default **3**); after the
  budget is exhausted the poller **logs a terminal failure** and ignores that
  event on later polls; a dead tmux session is **respawned** so a retry can
  actually land; and a **new** event (e.g. a fresh comment) on the same work
  item **retriggers** processing with a fresh budget.
- **Actual:** a failed delivery into a dead tmux session loops forever; a failed
  spawn/forward on the poll path is baselined as "processed" and never retried;
  there is no attempt limit and no give-up log.

## Root cause (confirmed)

- `TmuxRunner.deliver` (`runner.py`) fails closed when `has_session` is false but
  gives no distinct signal, so `Dispatcher._dispatch_one` treats a *terminal*
  "session gone" identically to a *transient* fault — release for redelivery,
  never respawn. The dispatcher already knows how to spawn a tmux session
  (`_spawn_tmux`); it just never invokes it on the delivery path.
- `Poller._process_item` calls `state.update(...)` unconditionally at the end of
  every cycle, before it can possibly know the dispatch outcome (dispatch is
  async — `dispatcher.handle` enqueues and returns). So success and failure are
  both recorded as "seen", and the spawn-retry guard `(first_sight or
  new_comments)` can never fire again once the item is "known".

## Acceptance criteria (EARS)

### Configurable retry budget (poll path)

1. The system SHALL expose a configurable per-event retry budget
   (`polling.maxRetries`, default **3**).
2. WHEN the poller forwards a comment to a work item's session AND the dispatch
   does not succeed THEN the system SHALL re-forward that comment on later poll
   cycles until it succeeds or the budget is exhausted, rather than baselining
   it as processed after the first attempt.
3. WHEN the poller spawns a session for a labelled item AND the spawn does not
   succeed (no session appears) THEN the system SHALL retry the spawn on later
   cycles until a session exists or the budget is exhausted — a failed spawn
   SHALL NOT suppress subsequent spawn attempts.
4. WHEN a comment's or spawn's retry budget is exhausted THEN the system SHALL
   emit a terminal failure record in the event log (`will_retry: false`) and
   thereafter ignore that event on later polls (no infinite retry).
5. WHEN a delivery is still in flight (enqueued/processing) THEN the system
   SHALL NOT count it as a failed attempt, so a long-running dispatch is never
   mistaken for a failure and prematurely given up.
6. WHEN a **new** event (e.g. a new comment) arrives on a work item THEN it
   SHALL be processed with its own fresh retry budget, and SHALL re-arm a spawn
   that had previously been given up (a new comment retriggers the item).

### Respawn a dead tmux session (delivery path)

1. WHEN a routed event is delivered to a tmux-mode session AND that session's
   tmux session is not found (crashed or killed) THEN the system SHALL respawn
   the harness in a fresh tmux session for the same work item and deliver the
   pending event into it (as its boot prompt), so the event is not dropped and
   the next delivery/retry can land. (AC7)
2. WHEN delivery fails for a reason **other** than a missing session (tmux
   unavailable, a paste sub-command errors while the session still exists) THEN
   the system SHALL keep the existing behaviour: fail the dispatch and release
   for retry, NOT respawn. (AC8)
3. WHEN a respawn cannot proceed (harness CLI missing, `tmux new-session` fails)
   THEN the system SHALL fail the dispatch and release for retry, emitting an
   observable failure record rather than silently dropping the event. (AC9)

### Observability

1. Respawns and terminal give-ups SHALL be observable via dedicated event-log
   types distinct from a first-time spawn / a transient error. (AC10)

## Out of scope

- **Bounding webhook (push) redelivery.** GitHub owns webhook redelivery cadence
  and count; the retry budget governs the **poll** (pull) path, where the-loop
  itself drives retries. The respawn fix (AC7–9) still repairs the webhook
  dead-session loop by making the next redelivery land.
- **Resuming the crashed harness conversation.** A respawn starts a fresh
  harness session; the prior in-memory TUI conversation is not recovered.
  the-loop resumes a work item from its checked-in artifacts (spec,
  `execution-log.md`, tasks) plus the delivered event. Interactive `--resume`
  of a dead session id is a separate enhancement (see design "Alternatives").
- **Proactive liveness monitoring.** Recovery is reactive (driven by a delivery
  or a poll cycle), not an independent health poller.

## Security considerations

No new attack surface. Retry accounting and respawn are parameterised entirely
by **already-recorded, previously-validated** state — the durable poll state
(comment ids the-loop itself observed) and the session registry (work item,
harness, cwd/worktree, tmux target). No new external input decides what, where,
or how often to spawn. The event that triggers a respawn is still rendered
through the same untrusted-payload template (payload framed as data, never
instructions), and the upstream authorized-actor guard is unchanged. Retries are
**bounded** (default 3) and give up fail-closed with an audit record, so a
crashing harness or a hostile flood cannot induce unbounded spawning: the poll
path caps attempts per event, and each attempt is one-per-cycle on the
serialized per-work-item worker.

## Open questions

None. (Retry budget lives on the poll path; webhook redelivery stays
GitHub-driven — see Out of scope. Confirmed against the reporter's comments:
configurable, default 3; log-and-ignore after exhaustion; new comment
retriggers.)
