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
- [x] **T2 — Config key.** `routing.pauseFile` in
      `RoutingConfig`, `.the-loop/cli-config.schema.json`,
      `skills/the-loop/templates/cli-config.yaml`, `.the-loop/cli-config.yaml`.
      _(R8.3)_
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
- [x] **T8 — CLI subcommands.** `sessions list` (rewritten on `build_rows`),
      `show`, `pause`, `resume`, `prune`.
      _(R1–R4, R7)_
- [x] **T9 — Unit tests.** `test_pauses.py`, `test_overview.py`,
      `test_sessions_command.py`, `test_state.py`. _(all)_
- [x] **T10 — Integration tests.** `test_pause_integration.py` with Gherkin
      docstrings: poller ignores + baselines while paused; label-only pause stops
      webhook dispatch; a paused item's closure still closes its session.
      _(R3.2, R3.3, R3.4, R3.6, R5.1)_
- [x] **T11 — Docs.** `cli/README.md` (subcommands, flags, sample output, config
      table), `docs/capabilities/cli.md`, `docs/capabilities/interactive-sessions.md`,
      `skills/the-loop/reference/automation.md`.
      _(R8.1, R8.2)_
- [x] **T13 — Review follow-up: `commands/sessions_cmd.py` → `commands/sessions.py`**
      (+ `tests/test_sessions_cmd.py` → `tests/test_sessions_command.py`). _(review)_
- [x] **T14 — Review follow-up: consolidate runtime state under `.the-loop/state/`.**
      `the_loop/state.py` (path table, pre-move fallback, `migrate`), new
      `the-loop state paths|migrate` command, six defaults repointed, schema +
      template + repo config + `.gitignore`, `test_state.py`, decision-040.
      _(R9)_
- [~] **T7/T15 — Label-driven pause + `labels ensure` — REMOVED from this PR.**
      Built, reviewed, then pulled at the owner's request to keep #100 to CLI
      session management; carried to a follow-up issue with the research
      findings (see requirements R5). _(deferred)_
- [x] **T12 — Gates.** `ruff`, `pyright`, `pytest` green; execution log updated;
      PR briefing posted. _(process)_
