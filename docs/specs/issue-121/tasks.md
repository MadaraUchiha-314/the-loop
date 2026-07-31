---
type: tasks
phase: tasks-breakdown
workItem: issue-121
status: approved             # draft | in-review | approved
approvedBy: []               # tier-3: the human gate is the PR review — see execution-log
overrides: {}
---

# Tasks: one harness-config reader, one recorded rule

> Phase 3 of 3 (requirements → design → tasks). A DAG of implementation tasks derived
> from the approved design. MUST be reviewed/approved before implementation begins.

## Task list

TDD invariant (`tdd.mode: standard`): **T1 writes the failing test first.** H1–H4 cannot
pass before `harness_config.READS` exists (H1/H3/H4) or while three modules still open the
file themselves (H2), so the red is genuine and each later task turns one part green.

- [x] 1. **The pin, red.** `cli/tests/test_harness_config.py` with H1–H4 from design A3,
      plus the loader unit tests from the testing strategy. Stdlib + PyYAML only; the doc
      halves skip when `docs/` is absent.
  - **Depends on:** none
  - **Requirements:** R4.1–R4.5
  - **Test:** `uv run --project cli python -m pytest cli/tests/test_harness_config.py`
    — **red**: no `the_loop.harness_config` module

- [x] 2. **The shared reader.** `cli/the_loop/harness_config.py`: `FILENAMES`,
      `HarnessConfigError`, `config_path`, `load`, `load_strict`, `HarnessConfigRead`,
      `READS`. Module docstring states the direction rule and points at decision-044.
  - **Depends on:** 1
  - **Requirements:** R3.1, R3.2, R3.3, R4.1
  - **Test:** the loader unit tests and H1 green; H2/H3/H4 still red

- [x] 3. **Collapse the three call sites.** `graph/bootstrap.py` re-exports
      `load_harness_config` from the module (keeping `__all__`); `critics.py`'s
      `config_path` becomes an alias and `load_critics` uses `load_strict`, re-raising as
      `CriticConfigError`; `commands/scenarios.py::_load_config_globs` reads
      `harness_config.load`. No pre-existing test edited.
  - **Depends on:** 2
  - **Requirements:** R3.1, R3.3, R3.4, R5.1, R5.2
  - **Test:** H2 green; `test_critics.py`, `test_critics_integration.py`, `test_cli.py`,
    `test_graph_*.py` all pass **unmodified**

- [x] 4. **Decision-044.** `docs/decisions/decision-044.md` — the invariant, both
      directions, the three readers and their keys, the four rejection reasons, the
      relationship to decision-032. Add the row to `docs/decisions/decisions.md`.
  - **Depends on:** none
  - **Requirements:** R1.1, R1.2, R1.3
  - **Test:** `markdownlint` green; the record is linked from every page changed in T5

- [x] 5. **Correct the four false claims + document the read surface.**
      `docs/config/index.md`, `docs/cli/concepts.md`, `docs/cli/commands/index.md`,
      `docs/cli/index.md` (prose + Mermaid), `docs/cli/extending.md`, and the new
      "What the CLI reads from it" section in `docs/config/harness-config.md`.
  - **Depends on:** 4
  - **Requirements:** R2.1, R2.2, R2.3, R2.4
  - **Test:** H3/H4 green; `markdownlint` green; no page still asserts "never"

- [x] 6. **Capability docs.** `docs/capabilities/cli.md`: the invariant in the behaviour
      section, and a history row for issue-121.
  - **Depends on:** 5
  - **Requirements:** R5.3
  - **Test:** `markdownlint` green

- [x] 7. **Full gates + the process gate.** `make check` green; `uv run the-loop check
      issue-121 --recompute --fail-on block` exit 0. Execution log updated with evidence.
  - **Depends on:** 3, 6
  - **Requirements:** R5.1, R5.2
  - **Test:** `make check`; `the-loop check issue-121`

## Out of scope

- Removing the pre-rename `.the-loop/config.yaml` fallback (decision-035 compatibility).
- Any per-repository override of harness policy from `cli-config.yaml` — rejected in
  design § Alternatives.
- The `bugfix.md` vs `requirements.md` graph mismatch raised on PR #120; unrelated.
