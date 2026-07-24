---
type: tasks
phase: tasks-breakdown
workItem: issue-80
status: draft
approvedBy: []
collaborators: [engineer]
overrides: {}
---

# Tasks: bounded per-event retry policy + respawn dead tmux sessions

> Phase 3 of 3 (bugfix → design → tasks). DAG — a task starts once its
> dependencies are checked.

- [x] **T1 — `TmuxResult.session_missing`.** Add `session_missing: bool = False`
  to `TmuxResult`; set it `True` on `TmuxRunner.deliver`'s `has_session`-false
  early return. *(AC7, AC8)*
- [x] **T2 — `Dispatcher.delivery_status`.** Add `delivery_status(delivery_id,
  refs) -> "done"|"inflight"|"unhandled"` reading `recent_deliveries` (done),
  the dedup cache (inflight), else unhandled. *(AC2, AC5)* — depends on nothing.
- [x] **T3 — Respawn on delivery.** In `_dispatch_one`, when the tmux delivery
  fails and `result.session_missing`, call new `_respawn_tmux(session, routed,
  prompt)`: reuse `session.harness`/`cwd`/`tmux_target`, mint a new id, `tmux.spawn`
  with the event prompt as boot prompt, re-register (`force=True`, preserving
  `recent_deliveries`), `touch`, emit `session.respawned`; fail-closed + release
  on any inability. *(AC7, AC9)* — depends on T1.
- [x] **T4 — `polling.maxRetries` config.** Add to `.the-loop/cli-config.schema.json`
  (integer, default 3, min 1) and `.the-loop/cli-config.yaml`; mirror on
  `PollConfig` (`from_mapping`) and add a `--max-retries` flag to `poll start`.
  *(AC1)*
- [x] **T5 — `PollState` retry ledger.** Replace the flat baseline with
  `seenComments` (resolved) + `commentAttempts` + `spawn` ({attempts, gaveUp,
  deliveryId}); add accessors and `finalize(ref, live_ids, polled_at)` pruning
  both maps to the live thread. Round-trips through the JSON file. *(AC2–AC6)*
- [x] **T6 — `_process_item` retry flow.** Rewrite to: baseline dropped
  (unauthorized/self) comments; arm/retry the spawn with the budget (`_try_spawn`,
  armed by first sight / new activity / in-progress, re-armed by a new comment);
  process each unresolved candidate comment via `delivery_status` (done→resolve,
  inflight→wait, unhandled→retry/give-up); `finalize` at cycle end. Emit
  `poll.spawn_failed`/`poll.comment_failed` on give-up and add `attempt` to
  `poll.comment_forwarded`. Add `failures` to `PollSummary`/`poll.cycle`.
  *(AC2–AC6)* — depends on T2, T4, T5.
- [x] **T7 — Event types.** Register `session.respawned`, `poll.spawn_failed`,
  `poll.comment_failed` in `EVENT_TYPES`; note `attempt` on
  `poll.comment_forwarded`. *(AC10)* — depends on T3, T6.
- [x] **T8 — Tests.** Unit: `session_missing` (T1), `delivery_status` (T2),
  `PollState` ledger (T5). Integration: respawn-on-dead-session + no-respawn on
  other failure (`test_tmux_runner_integration.py`); comment retry→give-up→
  ignore, new-comment-retriggers, success-baselines (`test_poller_integration.py`
  / `test_poller.py`) — Gherkin docstrings + requirement links. *(all AC)* —
  depends on T1–T7.
- [x] **T9 — Capability docs.** Update `docs/capabilities/interactive-sessions.md`
  (respawn) and `docs/capabilities/webhook-triggers.md` / the poller capability
  doc (retry policy) with current behaviour + history rows.
- [x] **T10 — Gates.** `ruff check` / `ruff format --check`, `pyright`, `pytest`
  all green; update `execution-log.md`.
