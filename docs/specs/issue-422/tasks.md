---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#422"
status: in-review
approvedBy: []
overrides: {}
riskTier: 3
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: the suite writes into the checked-in `.the-loop/` when run from the repo root

> Phase 4 of 4. Each task names the acceptance criterion it satisfies and the
> testing-plan row that proves it. Ordered as the ticket asks: stop new debris, remove the
> old, then make the next instance loud. The guard is written first so it can fail on the
> unfixed tree.

- [x] **A0 — reproduce, and find the writer.** Full suite from the root on `main`: the
      tracked record is rewritten. A `sitecustomize` tracer names every write under either
      `.the-loop/` with its stack. *AC:* AC1 · *Test:* T15.
- [x] **A1 — the guard.** `cli/tests/conftest.py`: the audit hook, the autouse
      `_no_protected_state_writes` fixture, and `pytest_sessionfinish`. Run before any
      fix: it fails four tests, seven cases. *AC:* AC4 · *Test:* T3.
- [x] **A2 — the four writers.** `_dispatcher`'s `portable_dir`; the restart test's
      `eventlog.configure` call, plus a non-empty-log assertion; the health test's config
      file and `$THE_LOOP_CLI_CONFIG`; `probe_subscription` / `report_subscription` /
      `_subscription_lines` take `cli_config`, and the doctor test asserts the cache
      location. *Deps:* A1 · *AC:* AC1, AC2, AC5 · *Test:* T1, T2, T5.
- [x] **A3 — the guard's own tests.** `cli/tests/test_state_isolation.py`. *Deps:* A1 ·
      *AC:* AC4 · *Test:* T4.
- [x] **B1 — remove the debris.** `git rm` both files under `.the-loop/portable/`; reword
      `.gitignore`'s `cli/.the-loop/` comment. *AC:* AC3 · *Test:* T1.
- [x] **C1 — docs.** `docs/capabilities/testing-and-contracts.md` gains the rule and a
      history row. `docs/capabilities/channels.md` records that the probe resolves names
      through the state-root cache, with a history row. *Deps:* A2 · *Test:* T6.
- [x] **D1 — evidence.** `verification.md`, `self-review.md`, `security-review.md`,
      `documentation.md`, `reviewer-briefing.md`. *Deps:* A1–C1.
