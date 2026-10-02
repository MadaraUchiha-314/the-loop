---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#454"
status: in-review
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: the CLI suite reads the machine it runs on

> Phase 4 of 4. Each task names the acceptance criterion it satisfies and the
> testing-plan row that proves it.

- [x] **A0 — reproduce on Linux.** Recreate each host condition (stub harness CLIs on
      PATH, no tmux, a symlinked `TMPDIR`) and confirm the ticket's failures, plus the
      tmux-preflight failures the operator saw as "unrelated ingress failures".
      *AC:* R5 · *Test:* T6.
- [x] **A1 — critic availability.** Fix `shutil.which` in
      `test_critics_lists_the_cli_configs_entries_without_argv` (parametrised over
      installed / not installed) and `test_list_reports_availability` (adds a critic that
      resolves). *AC:* R1.1, R1.2 · *Test:* T1.
- [x] **A2 — canonical containment.** Compare lexically and canonically, parametrised
      over four hostile refs; add the symlinked-temp-dir test. *AC:* R2.1–R2.3 ·
      *Test:* T2.
- [x] **A3 — process metadata.** `_stat()` reads `os.getsid`/`os.getpgid`; `ppid` from
      `/proc` or `ps -o ppid=`. Assertions unchanged. *AC:* R3.1, R3.2 · *Test:* T3, T4.
- [x] **A4 — explicit tmux.** `preflight_tmux` fixture in `conftest.py` with a teardown
      tripwire; both daemon modules' `env` fixtures prepend it to the subprocess PATH.
      *AC:* R4.1, R4.2 · *Test:* T5, T7.
- [x] **B1 — docs.** `docs/capabilities/testing-and-contracts.md`: a requirement section
      and a history row. *Deps:* A1–A4 · *Test:* T9.
- [x] **C1 — verify and record.** Host matrix red and green, normal-host run, static
      checks; `evidence/verification.md`, `self-review.md`, `security-review.md`,
      `documentation.md`, `reviewer-briefing.md`. *Deps:* A1–B1 · *Test:* T6–T9.
