---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#412"
status: approved
approvedBy: ["the-loop"]
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: four `test_instance.py` tests read the machine they run on

> Phase 4 of 4. Each task names the acceptance criterion it satisfies and the
> testing-plan row that proves it. Ordered as the ticket asks: the bug first, the
> parity second, so the parity fix is not what hides the next divergence.

- [x] **A0 — reproduce, and pin the negative control.** Run the four tests in all four
      rows of the ticket's table on `main`; confirm 4 failed / 59 passed in three of
      them. *AC:* AC1 · *Test:* T5.
- [x] **A1 — pin the lookup where the defect is.** `cli/tests/test_instance.py` gains the
      autouse `_no_ambient_cli_config` fixture, setting `$THE_LOOP_CLI_CONFIG` to an
      uncreated path under the test's own `tmp_path`, so `default_cli_config_path()` and
      `_cli_config_export()` still run for real and find nothing. *AC:* AC1 ·
      *Test:* T1, T11.
- [x] **A2 — establish the scope by trying the wider one.** The same fixture in
      `cli/tests/conftest.py`, suite-wide, then run T2. It fails 14 tests whose state root
      is anchored on the config path; revert to A1 and record why in `bugfix.md` § Defect 1
      and `evidence/verification.md`. *AC:* AC1 · *Test:* T2.
- [x] **B1 — make the Makefile's parity claim true.** `test:` becomes
      `cd cli && uv run python -m pytest -q`, byte-for-byte the pre-commit `pytest` hook's
      entry; a `# CI parity:` comment says why the `cd` is part of the command; the header
      RULE is narrowed from "all scripts run from the project root" to invocation, naming
      the exception. *Deps:* A1 (the ticket's order) · *AC:* AC2, AC3 · *Test:* T4.
- [x] **C1 — docs.** `docs/capabilities/testing-and-contracts.md` gains the standing rule
      (a test pins or controls what it resolves; a cwd-relative lookup is not ambient in
      itself and is not pinned wholesale; a `Makefile` parity claim includes the working
      directory) and a history row. *Deps:* A1, B1 · *Test:* T4 (markdownlint via
      `make lint`).
- [x] **D1 — evidence.** `verification.md` (all matrix rows with raw output, including the
      rejected suite-wide variant), `self-review.md`, `security-review.md`,
      `documentation.md`, `reviewer-briefing.md`. *Deps:* A1–C1.
