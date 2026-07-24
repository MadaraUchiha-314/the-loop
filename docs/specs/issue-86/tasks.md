---
type: tasks
phase: tasks-breakdown
workItem: "issue-86"
status: draft
approvedBy: []
collaborators: [engineer]
overrides: {}
---

# Tasks: retained tmux sessions + session announcement comments

> Phase 3 of 3 (requirements → design → tasks). DAG — a task starts once its
> dependencies are checked.

- [x] **T1 — tmux `remain-on-exit` + pane liveness.** `runner.py`:
  `TmuxResult.output`; `TmuxRunner(remain_on_exit=True)`; best-effort
  `set-option -w remain-on-exit on` after spawn; `has_live_session()` via
  `list-panes -F "#{pane_dead}"`; `deliver()` guards on liveness.
  *(AC2.1–2.3)* — depends on nothing.
- [x] **T2 — `AnnounceConfig` + `announcement_body`.** New
  `cli/the_loop/announce.py`: config mirror with `from_mapping`, pure body
  builder using only registry-derived fields. *(AC3.1, AC3.2, AC3.5, AC3.6)* —
  depends on nothing.
- [x] **T3 — `SessionAnnouncer`.** No-op ladder (disabled, non-tmux,
  non-github, malformed owner/repo, missing `gh` warn-once), `gh api` POST to
  the issue comments endpoint, `session.announced` /
  `session.announce_failed`, never raises. *(AC3.1–3.5, AC4.2, AC4.3)* —
  depends on T2.
- [x] **T4 — Dispatcher retention.** `TmuxConfig` in `RoutingConfig`; runner
  built with `remain_on_exit`; PR-close keeps the tmux session by default,
  logging the attach command and emitting `session.retained`; kills when
  `keepSessionOnClose: false`. *(AC1.1, AC1.2, AC1.4, AC1.6, AC4.1)* — depends
  on T1.
- [x] **T5 — Dispatcher announcement.** Optional `announcer` ctor param
  (override survives `reload`); `_spawn_tmux` announces after registration
  without affecting its return value; `_respawn_tmux` deliberately does not
  (first spawn only). *(AC3.1–3.4)* — depends on T3, T4.
- [x] **T6 — `sessions close` / `sessions attach`.** `close` honours
  `keepSessionOnClose` with `--keep-tmux` / `--kill-tmux` overrides; `attach`
  falls back to a **closed** work item's retained session (with a note) and
  stops refusing dead panes. *(AC1.3, AC2.4, AC2.5)* — depends on T1, T4.
- [x] **T7 — Event-log types.** Register `session.retained`,
  `session.announced`, `session.announce_failed` in `eventlog.EVENT_TYPES`.
  *(AC4)* — depends on nothing.
- [x] **T8 — Config schema + example.** `routing.tmux` and `routing.announce`
  in `.the-loop/cli-config.schema.json` (defaults documented) and the dogfood
  blocks in `.the-loop/cli-config.yaml` (+ the packaged template if it carries
  the same blocks); `make validate` green. *(AC1.2, AC3.5)* — depends on T1, T2.
- [x] **T9 — Unit tests.** `test_announce.py` plus the `test_tmux_runner.py`
  additions per the design's testing strategy. — depends on T1–T3.
- [x] **T10 — Integration + CLI tests.** Retention / kill-on-close, respawn
  through a dead retained pane, announce-on-spawn, no re-announce on respawn,
  no-announce for process mode, announcer failure is inert; `sessions close --keep/--kill-tmux`
  and `sessions attach` to a closed-but-retained session. — depends on T5, T6.
- [x] **T11 — Docs.** `cli/README.md` config tables + `sessions` command notes;
  `docs/capabilities/interactive-sessions.md` behaviour bullets and history
  row. — depends on T5, T6.
- [x] **T12 — Gates.** `make check` (ruff, markdownlint, format, pyright,
  validate, pytest) fully green; evidence in `execution-log.md`. — depends on
  T1–T11.
