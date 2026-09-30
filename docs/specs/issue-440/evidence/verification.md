---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#440"
---

<!-- Authored per the the-loop:writing skill. -->

# Verification: the harness is a per-work-item choice at `phase-selection`

> The `verification` node's record, one row per row of
> [`testing-plan.md`](../testing-plan.md). Environment: Python 3.11.15, `uv` 0.12.19,
> `uv sync` against the committed `uv.lock`. No harness binary is executed.

## Verification results

| Row | Command | Outcome |
|-----|---------|---------|
| T1 | `tests/test_selection_harness.py` (vocabulary, bootstrap), `tests/test_modelchoice.py` | pass |
| T2–T5 | `tests/test_selection_harness.py` | **26 passed** |
| T6 | `tests/test_dispatcher_harness.py` | **8 passed** |
| T7 | `tests/test_selection_control.py` (prefix pin) | pass |
| T8 | the two new modules with `cli/the_loop` stashed (tests kept) | `test_selection_harness.py` fails to import (`hosting_harnesses` does not exist); `test_dispatcher_harness.py` **6 failed, 2 passed** — the two that pass pin unchanged behaviour (no frozen harness → default; a live session keeps its harness) |
| T9 | `cd cli && uv run python -m pytest -q` (CI's command) | **5017 passed, 1 skipped** in 204 s |
| T10 | `ruff format --check`, `ruff check`, `pyright cli`, `scripts/validate_config.py`, `markdownlint-cli2` on every changed Markdown file | all green |
| T11–T14 | — | n/a, as the plan states |
