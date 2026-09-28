---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#426"
status: in-review
approvedBy: []
overrides: {}
riskTier: 3
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: work-item mode launches Claude Code without its question menu

> Phase 4 of 4. Each task names the requirement it satisfies and the testing-plan row
> that proves it.

## Task list

- [x] **A0: reproduce.** The real CLI's parsing of both spellings. *Req:* R1.3, R1.4 ·
      *Test:* T8.
- [x] **A1: `InteractionConfig.unattended`.** *Req:* R2.1, R2.2 · *Test:* T2.
- [x] **A2: the adapter carries the fact.** `HarnessAdapter.unattended`,
      `_UNATTENDED_ARGS`, `with_unattended`, `_launch_args`; Claude's token and both
      `interactive_*` methods. *Req:* R1.3, R1.4, R3.2, R3.3 · *Test:* T1.
- [x] **A3: the launch seams set it.** `Dispatcher._adapter_for` and
      `core.sessions._restart_adapter`. *Deps:* A1, A2 · *Req:* R1.1, R1.2, R2.3,
      R2.4, R3.1 · *Test:* T3–T6.
- [x] **A4: tests.** New cases in `test_tmux_runner.py`, `test_interaction.py`,
      `test_tmux_runner_integration.py`, `test_interaction_integration.py` and
      `test_sessions_restart_integration.py`. *Deps:* A1–A3 · *Test:*
      T1–T5, T7.
- [x] **B1: docs.** `docs/capabilities/webhook-triggers.md` and
      `docs/capabilities/interactive-sessions.md` get the requirement and a history
      row; `docs/config/cli/routing-options.md` (`interaction.mode`) and
      `docs/config/cli/harnesses-options.md` (`harnesses[].args`: the variadic
      hazard); `skills/the-loop/reference/collaboration.md` and `automation.md`.
      *Deps:* A3.
- [ ] **C1: real TUI evidence.** *Deps:* A2 · *Test:* T9. Blocked in this
      environment (the TUI stops at its login screen); T9b stands in, and
      `evidence/verification.md` § T9 has the commands to close it.
- [x] **D1: evidence.** `verification.md`, `self-review.md`, `security-review.md`,
      `documentation.md`, `reviewer-briefing.md`. *Deps:* A0–C1.
