---
type: tasks
phase: tasks-breakdown
workItem: "issue-94"
status: draft
approvedBy: []
collaborators: [engineer]
overrides: {}
---

# Tasks: closing a work item ends its harness session

> Phase 3 of 3 (requirements → design → tasks). DAG — a task starts once its
> dependencies are checked.

- [x] **T1 — provider contract.** `poller/base.py`: `Closure` dataclass and
  `PollProvider.owns` / `closure` / `closure_event` with opt-in defaults.
  *(AC1.7)* — depends on nothing.
- [x] **T2 — GitHub closure.** `poller/github.py`: `GhClient.fetch_item_state`
  (`gh api repos/{o}/{r}/issues/{n}`, merged via `pull_request.merged_at`) and
  the provider's `owns`/`closure`/`closure_event`. *(AC1.2, AC1.6, AC1.7)* —
  depends on T1.
- [x] **T3 — poller reconciliation.** `poller/poller.py`: `open_refs` from the
  successful listing, `_reconcile_closures`, `PollSummary.closures`,
  `PollState.forget`. *(AC1.1–AC1.6)* — depends on T1.
- [x] **T4 — close is close.** `webhook/dispatcher.py`: `_is_close_event` /
  `_close_reason` replacing `_is_pr_close`, `reason` on `session.autoclosed`;
  `webhook/router.py`: lifecycle exemption widened to `issues`/`closed`.
  *(AC2.1–AC2.4)* — depends on nothing.
- [x] **T5 — terminate the harness.** `runner.py`:
  `TmuxRunner.live_pane_pids` + `terminate_harness(session, grace, timeout,
  sleeper, killer)`; `dispatcher._close_tmux` calling it when retaining.
  *(AC3.1–AC3.7)* — depends on T4 (same close path) + T6 (config).
- [x] **T6 — config mirror.** `TmuxConfig.kill_harness_on_close` /
  `harness_kill_grace_seconds` from `killHarnessOnClose` /
  `harnessKillGraceSeconds`, hot-reloading with `RoutingConfig`. *(AC5.1)* —
  depends on nothing.
- [x] **T7 — CLI parity.** `sessions close` terminates the harness on the
  retain path; `sessions attach` forces `-r` for a closed session. *(AC3.1,
  AC4.1, AC4.2)* — depends on T5.
- [x] **T8 — observability.** `poll.closure_detected` and
  `session.harness_terminated` registered in `eventlog.EVENT_TYPES`; `reason`
  documented on `session.autoclosed`; cycle log/`poll.cycle` carry `closures`.
  *(AC5.2)* — depends on T3, T4, T5.
- [x] **T9 — config schema + examples.** `killHarnessOnClose` /
  `harnessKillGraceSeconds` under `routing.tmux` in
  `.the-loop/cli-config.schema.json`, the dogfood `.the-loop/cli-config.yaml`
  and the packaged `skills/the-loop/templates/cli-config.yaml`; `make validate`
  green. *(AC5.1)* — depends on T6.
- [x] **T10 — unit tests.** Provider closure mapping + `owns`, `PollState.forget`,
  `TmuxConfig` parsing, `_is_close_event`/`_close_reason`, `terminate_harness`
  (SIGTERM happy path, SIGKILL escalation, dead pane, missing session,
  `ProcessLookupError`). — depends on T1–T7.
- [x] **T11 — integration tests.** Poll-cycle closure scenarios (issue closed,
  PR merged, listing error, closure error, still-open item, reopen re-spawns),
  the webhook `issues`/`closed` scenario, and stub-tmux close scenarios
  (terminate + retain, opt-out, kill-tmux). — depends on T3, T4, T5.
- [x] **T12 — docs.** `cli/README.md` config rows + prose;
  `docs/capabilities/interactive-sessions.md` and
  `docs/capabilities/webhook-triggers.md` behaviour bullets + history rows;
  the webhook event prompt template's parenthetical. *(AC5.3)* — depends on
  T1–T9.
- [x] **T13 — gates.** `make check` fully green; evidence in
  `execution-log.md`; PR + reviewer briefing. — depends on T1–T12.
