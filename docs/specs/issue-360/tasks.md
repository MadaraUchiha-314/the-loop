---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#360"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Tasks: the cursor adapter's model flag

> Phase 3 of 3. Each task names the requirement it serves and the testing-plan row that
> proves it. TDD: the red root (T1) is written and run **before** the fix.

- [x] **1. Red root — assert the argv the CLI actually parses.**
  Add `test_cursor_oneshot_argv_uses_the_long_model_flag` to `cli/tests/test_critics.py`
  and correct `test_a_model_resolves_through_the_adapters_flag` in
  `cli/tests/test_modelchoice.py`. Run them and capture the failure verbatim as
  `evidence/red.md`.
  _Requirements: R1.1, R1.4 — Test: T1_

- [x] **2. Fix the flag.**
  `CursorAgentAdapter.model_flag = "--model"` in `cli/the_loop/harness/cursor_agent.py`,
  with a comment recording that `cursor-agent --help` lists no short form and what `-m`
  cost, so the next reader does not re-derive it.
  _Requirements: R1.1, R1.2, R1.3 — Test: T1, T2_

- [x] **3. Correct the assertion that should have caught it.**
  `test_builtin_harness_derives_argv_from_the_adapter` in `cli/tests/test_critics.py`
  pinned the critic's end-to-end argv to `-m`. Correct it — it is the one test that
  exercised the whole seam and agreed with the bug.
  _Requirements: R1.2 — Test: T2_

- [x] **4. Prove the verdict cache needs no migration.**
  Add `test_a_verdict_probed_with_the_old_cursor_flag_no_longer_withholds` to
  `cli/tests/test_modelprobe.py`: a `refused` cached against `("-m", name)` does not
  withhold once the resolved args are `("--model", name)`.
  _Requirements: design D3 — Test: T3_

- [x] **5. Write the rule down where current behaviour lives.**
  `docs/capabilities/review-loop.md`: a `model_flag` is a spelling the harness's own
  `--help` lists (the long form where both exist), the value for each shipped adapter,
  and a History row for issue-360.
  _Requirements: R2.1, R2.2 — Test: T13_

- [x] **6. Verify and record.**
  Run the matrix's applicable rows and `make check`; record the outcome in
  `testing-plan.md` §Verification results and `evidence/verification.md`; complete the
  execution log, the security-review gate and the PR briefing.
  _Requirements: R1.4 — Test: T1, T2, T3, T10, T13_
