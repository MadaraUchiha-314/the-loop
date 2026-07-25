---
type: tasks
phase: tasks-breakdown
workItem: "issue-89"
status: draft
approvedBy: []
collaborators: [engineer]
overrides: {}
---

# Tasks: resume-on-respawn for tmux-hosted sessions

> Phase 3 of 3 (requirements → design → tasks). DAG — a task starts once its
> dependencies are checked.

- [x] **T1 — adapter contract.** `harness/base.py`:
  `interactive_resume_argv(prompt, session_id)` raising `UnsupportedRunnerError`
  by default; `harness/claude_code.py`: `--resume <id> … <prompt>`. *(AC1.1,
  AC1.4)* — depends on nothing.
- [x] **T2 — runner support.** `runner.py`: `TmuxRunner.spawn(..., resume=False)`
  selecting the resume argv; `survived(target, delay, sleeper=time.sleep)`
  (no wait when `delay <= 0`) over `has_live_session`. *(AC1.1, AC2.1, AC2.4,
  AC2.5)* — depends on T1.
- [x] **T3 — config mirror.** `TmuxConfig.resume_on_respawn` (default true) and
  `resume_probe_seconds` (default 2.0) parsed from `resumeOnRespawn` /
  `resumeProbeSeconds`, hot-reloading with `RoutingConfig`. *(AC1.3, AC4.1,
  AC4.2, AC4.3)* — depends on nothing.
- [x] **T4 — dispatcher resume-then-fall-back.** `_try_resume` (opt-out, missing
  id, shape check, unsupported harness, failed spawn, dead pane → `None`) and
  `_respawn_tmux` using it: same id kept in the registry on success, `uuid4()`
  fresh spawn otherwise, existing failure handling untouched, still no
  announcement. *(AC1.1, AC1.2, AC1.3, AC1.4, AC1.5, AC2.2, AC2.3, AC2.6)* —
  depends on T2, T3.
- [x] **T5 — observability.** `resumed` on `session.respawned`; new
  `session.resume_failed` event type registered in `eventlog.EVENT_TYPES`;
  log lines distinguishing resumed vs fresh. *(AC3.1, AC3.2, AC3.3)* — depends
  on T4.
- [x] **T6 — config schema + examples.** `resumeOnRespawn` /
  `resumeProbeSeconds` under `routing.tmux` in
  `.the-loop/cli-config.schema.json`, plus the dogfood `.the-loop/cli-config.yaml`
  and the packaged `skills/the-loop/templates/cli-config.yaml`; `make validate`
  green. *(AC4.1)* — depends on T3.
- [x] **T7 — unit tests.** Adapter argv + unsupported-harness raise, runner
  resume spawn + `survived`, `TmuxConfig` parsing. — depends on T1–T3.
- [x] **T8 — integration tests.** Stub-tmux scenarios: respawn resumes the
  recorded id; a dead-on-arrival resume falls back to a fresh spawn carrying the
  same boot prompt; `resumeOnRespawn: false` respawns fresh; a resumed respawn
  posts no announcement. Update the issue-80/issue-86 respawn scenarios that
  asserted `--session-id`. — depends on T4, T5.
- [x] **T9 — docs.** `cli/README.md` config table rows;
  `docs/capabilities/interactive-sessions.md` behaviour bullet + history row.
  — depends on T4, T6.
- [ ] **T10 — gates.** `make check` fully green; evidence in `execution-log.md`;
  PR + reviewer briefing. — depends on T1–T9.
