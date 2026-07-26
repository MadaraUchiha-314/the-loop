---
type: tasks
phase: tasks-breakdown
workItem: "issue-98"
status: draft
approvedBy: []
collaborators: [engineer]
overrides: {}
---

# Tasks: `the-loop sessions` — one place to see and manage tracked work

> Phase 3 of 3. Each task names the requirements it satisfies. Order is
> dependency order; every task leaves the suite green.

- [x] **T1 — Pause ledger.** `the_loop/sessions/pauses.py`: `PauseRecord`,
      `PauseState`, `PauseStore` (atomic write, mtime-based reload, corrupt →
      empty + warning, label OR local). Export from `sessions/__init__.py`.
      _(R3.1, R3.7, R4.1, R4.3, R5.3, security/availability)_
- [x] **T2 — Config keys.** `routing.pausedLabel` + `routing.pauseFile` in
      `RoutingConfig`, `.the-loop/cli-config.schema.json`,
      `skills/the-loop/templates/cli-config.yaml`, `.the-loop/cli-config.yaml`.
      _(R5.1, R8.3)_
- [x] **T3 — Session fields.** `Session.owner_pid` / `pr_ref` / `pr_url` +
      `SessionRegistry.link_pr()`, backward-compatible `from_dict`.
      _(R2.3, R2.4)_
- [x] **T4 — Dispatcher.** Pause gate after the close branch (drop + discard
      delivery id + `dispatch.dropped reason=paused`); record `owner_pid` on
      spawn/respawn; `link_pr` on matched PR-carrying events.
      _(R3.3, R3.5, R3.6, R2.3, R2.4)_
- [x] **T5 — Poller.** Pause gate in `_process_item` that still baselines;
      `PollState.tracked_refs()` / `last_polled_at()` accessors for the CLI;
      wire `PauseStore` through `commands/poll.py`.
      _(R3.2, R3.4, R3.6, R1.1)_
- [x] **T6 — Overview join.** `the_loop/sessions/overview.py`: `Row`,
      `build_rows()`, `render_table()`, `render_detail()`, status ordering,
      URL derivation, tmux/process liveness.
      _(R1.1–R1.6, R2.1–R2.5, R5.5)_
- [x] **T7 — Labeler.** `the_loop/labels.py`: `LabelSpec`, `GitHubLabeler`
      (`ensure`/`add`/`remove`), argv validation, best-effort semantics.
      _(R5.4, R6.1–R6.3)_
- [x] **T8 — CLI subcommands.** `sessions list` (rewritten on `build_rows`),
      `show`, `pause`, `resume`, `prune`; `the-loop labels ensure`.
      _(R1–R5, R7)_
- [x] **T9 — Unit tests.** `test_pauses.py`, `test_overview.py`,
      `test_labels.py`, `test_sessions_cmd.py`. _(all)_
- [x] **T10 — Integration tests.** `test_pause_integration.py` with Gherkin
      docstrings: poller ignores + baselines while paused; label-only pause stops
      webhook dispatch; a paused item's closure still closes its session.
      _(R3.2, R3.3, R3.4, R3.6, R5.1)_
- [x] **T11 — Docs.** `cli/README.md` (subcommands, flags, sample output, config
      table), `docs/capabilities/cli.md`, `docs/capabilities/interactive-sessions.md`,
      `skills/the-loop/reference/automation.md`, `commands/init.md` step 4.
      _(R6.4, R8.1, R8.2)_
- [x] **T13 — Review follow-up: `commands/sessions_cmd.py` → `commands/sessions.py`**
      (+ `tests/test_sessions_cmd.py` → `tests/test_sessions_command.py`). _(review)_
- [x] **T14 — Review follow-up: consolidate runtime state under `.the-loop/state/`.**
      `the_loop/state.py` (path table, pre-move fallback, `migrate`), new
      `the-loop state paths|migrate` command, six defaults repointed, schema +
      template + repo config + `.gitignore`, `test_state.py`, decision-040.
      _(R9)_
- [x] **T15 — Review follow-up: the paused label is an authorized-only control.**
      Ledger records gain `source`/`by`; `state()` stops reading labels;
      `Dispatcher._apply_label_control` (sender-based, free);
      `Poller._reconcile_label_pause` + `PollProvider.label_actor` /
      `GhClient.label_actor` (issue-events API, only on a disagreement, refusals
      cached); `pause.unauthorized` event; R5 rewritten; decision-041.
      _(R5.1–R5.8)_
- [x] **T12 — Gates.** `ruff`, `pyright`, `pytest` green; execution log updated;
      PR briefing posted. _(process)_
