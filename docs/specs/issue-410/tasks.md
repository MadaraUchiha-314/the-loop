---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#410"
status: derived              # tasks.md has no approval gate (issue-281)
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: roll running sessions onto a refreshed environment

> Phase 4 of 4. Derived mechanically from [design.md](design.md) and
> [testing-plan.md](testing-plan.md). A DAG: tasks at the same indent are independent.

- [x] **1. `the_loop/envstate.py`** — `declared`, `fingerprint`, `process_environ`,
      `compare`. No value reaches a log line or a return value in clear except through
      the mapping `declared` returns. _Requirements: R1.1, R1.7, R2.1, R2.3, R5.2_
      _Test: T1_
  - [x] **1a.** `tests/test_envstate.py` — the pure comparisons, the fresh re-read, the
        real `/proc` read, and the `None` paths. _Test: T1_
- [x] **2. `TmuxRunner.respawn_in`** — `respawn-pane -k -t … -c … -e … -- <resume argv>`.
      _Requirements: R1.4_ _Test: T2_
- [x] **3. `TmuxRunner(env_provider=…)`** — fold the provider's names into `spawn_in`'s
      `-e` list behind `_supports_env`; the-loop's own three names last; default `None`
      leaves today's argv untouched. _Requirements: R4.1, R4.2, R4.3, R5.1_ _Test: T2_
  - [x] **3a.** Wire the provider at the two real construction sites (the dispatcher and
        the standing-session runner) so a spawn re-reads the file. _Requirements: R4.1_
  - [x] **3b.** `tests/test_tmux_runner.py` — argv assertions for 2, 3 and 3a. _Test: T2_
- [x] **4. `core.sessions.environment_drift`** — the read half: per session, its live
      pids, what they hold, and the names that differ. _Requirements: R3.1, R3.4_
      _Test: T4_
- [x] **5. `core.sessions.restart_sessions`** — selection, liveness, resumability,
      respawn, probe, verification, rows and exit code. _Requirements: R1.1–R1.7,
      R2.1–R2.4_ _Test: T3_
- [x] **6. `sessions restart` subcommand** — `--all`, `<work-item>`, `--dry-run`,
      `--format json`; renders core's rows. _Requirements: R1.1, R1.2, R1.3, R2.4_
      _Test: T3, T5_
- [x] **7. `status` reports drift** — `sessionEnvironment` in `lifecycle.status_all`,
      one line in each of the two renderers, `ok` untouched. _Requirements: R3.1–R3.5_
      _Test: T4_
- [x] **8. Tests** — `tests/test_sessions_restart_integration.py` covering T3, T4 and
      the redaction assertions of T6. _Test: T3, T4, T6_
- [x] **9. Docs** — `docs/cli/commands/sessions.md` (the subcommand, and the argv
      exposure stated plainly), `docs/cli/commands/status.md` (the new line),
      `docs/capabilities/interactive-sessions.md` (the capability). _Test: T5_
- [x] **10. Evidence** — verification (including the real-tmux transcript, T7), security
      review, self-review, documentation. _Test: T7, T8_
