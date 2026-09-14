---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#360"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: the cursor adapter's model flag

> Derived from `bugfix.md` and `design.md`, **before** `tasks.md` — each task's `_Test:_`
> names a row of the matrix below. Authored at `test-planning`, completed at
> `verification`. See `reference/testing.md`.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. This work item needs no credentials and touches no network.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the cursor one-shot argv carries `--model <name>` when a model is resolved (R1.1), and is byte-for-byte today's argv when none is (R1.3); `model_args` resolves through the corrected flag | `uv run --project cli python -m pytest -q cli/tests/test_critics.py cli/tests/test_modelchoice.py` |
| T2 | Unit | yes | a critic declared `harness: cursor` + `model:` resolves to the full `cursor-agent … --model <name>` argv (R1.2) — the end-to-end critic seam, one layer above T1 | `uv run --project cli python -m pytest -q cli/tests/test_critics.py -k builtin_harness` |
| T3 | Migration / upgrade | yes | a `refused` verdict cached against the `-m` argv no longer withholds the choice once the flag is `--model` (design D3) — no cache migration is needed | `uv run --project cli python -m pytest -q cli/tests/test_modelprobe.py` |
| T4 | Integration (scenario) | n/a — the defect is entirely in argv construction, which T1/T2 assert directly; an integration scenario would need a real `cursor-agent`, which is absent from CI and from this container | | |
| T5 | End-to-end | n/a — same reason as T4, plus a Cursor account. The reporter's live `cursor-agent` run in the ticket is the end-to-end evidence, recorded in `evidence/verification.md` as external | | |
| T6 | Contract (OpenAPI / GraphQL SDL) | n/a — no API surface changes; `docs/api-specs/` untouched | | |
| T7 | UI / visual | n/a — no user-facing surface (`design.md` §UI/UX) | | |
| T8 | Snapshot | n/a — the argv is asserted verbatim at T1/T2; a snapshot would restate it less legibly | | |
| T9 | Performance / load | n/a — one string constant on a path that already spawns a process | | |
| T10 | Security / abuse case | yes | the three abuse cases of `bugfix.md` are all "unchanged boundary", so the proof is that the boundary's existing negative tests still hold: no-shell argv, the claude adapter's argv untouched, and a name that resolves to nothing still `refused` | `uv run --project cli python -m pytest -q cli/tests/test_critics.py cli/tests/test_modelprobe.py cli/tests/test_modelchoice.py` |
| T11 | Accessibility | n/a — no rendered UI | | |
| T12 | Manual exploratory | n/a — there is nothing to explore that T1–T3 do not assert, and the one thing a human could add (a live `cursor-agent`) is T5's reason | | |
| T13 | Repository gates | yes | the whole repository still passes what CI runs: ruff, ruff format, pyright, config validation, the full suite, and markdownlint over every `**/*.md` — including this work item's own artifacts | `make check` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.4 | `test_cursor_oneshot_argv_uses_the_long_model_flag` (new) |
| T1 | R1.1 | `test_a_model_resolves_through_the_adapters_flag` (corrected from `-m`) |
| T1 | R1.3 | `test_oneshot_argv_without_a_model_is_the_plain_one_shot_run` (unchanged — it is the "no flag when no model" guard) |
| T2 | R1.2, R1.4 | `test_builtin_harness_derives_argv_from_the_adapter` (corrected from `-m`) |
| T3 | design D3 | `test_a_verdict_probed_with_the_old_cursor_flag_no_longer_withholds` (new) |
| T10 | bugfix.md §AC1 | `test_placeholder_value_with_metacharacters_stays_one_argument` and `test_the_prompt_reaches_the_critic_as_one_argument` — `run_critic` spawns a list argv with `shell=False` (`critics.py:446`), unchanged here |
| T10 | bugfix.md §AC2 | `test_an_effort_level_a_harness_cannot_express_is_refused_without_running` and `test_abuse_a_forged_verdict_cannot_introduce_a_choice` — a choice still has to be probed to be offered, and nothing outside the probe may introduce one |
| T10 | bugfix.md §AC3 | `test_oneshot_argv_appends_the_model_flag` (claude, unchanged) |
| T13 | R2.1, R2.2 | `make check` — markdownlint over the capability doc and these artifacts |

## Verification results

> Filled in at `verification`. Every row marked `yes` above is ticked here, with the
> command, the outcome, and where the evidence is committed.

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_critics.py cli/tests/test_modelchoice.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_critics.py -k builtin_harness`
- [x] T3 — `uv run --project cli python -m pytest -q cli/tests/test_modelprobe.py`
- [x] T10 — `uv run --project cli python -m pytest -q cli/tests/test_critics.py cli/tests/test_modelprobe.py cli/tests/test_modelchoice.py`
- [x] T13 — `make check`

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
| The failing state: the two new assertions and the corrected ones, before the fix | `pytest -q cli/tests/test_critics.py::…long_model_flag cli/tests/test_modelchoice.py::…adapters_flag` | fail (red, as designed) | [`evidence/red.md`](evidence/red.md) |
| T1, T2, T3, T10 — the argv, the critic seam, the verdict cache, the unchanged boundaries | `pytest -q cli/tests/test_critics.py cli/tests/test_modelchoice.py cli/tests/test_modelprobe.py` | pass | [`evidence/verification.md`](evidence/verification.md) |
| T13 — every repository gate CI runs | `make check` | pass | [`evidence/verification.md`](evidence/verification.md) |
