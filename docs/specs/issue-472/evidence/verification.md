---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#472"
---

# Verification (issue-472)

Run on 2026-10-06 on branch `claude/github-issue-472-56tziq`, using uv 0.12.23 (the
repository requires `>=0.12,<0.13`). GitHub is the tests' fake; the suite's autouse
fixture refuses any real socket.

## Activities

- [x] T1–T5 written first and seen red against the code before the change.
- [x] T1–T5 green after the change.
- [x] T6 full suite, ruff (lint and format), pyright, markdownlint, config validation.
- [x] T7 before and after renderings committed.
- [x] T8 security review (`security-review.md`).

## T1–T5: red before the change

The contract tests (rows read back, no fact lost) pass before and after, which is their
point: they guard what must not move.

```text
$ cd cli && uv run python -m pytest -q tests/test_selection_layout.py tests/test_channels_digest.py
FAILED tests/test_selection_layout.py::test_the_comment_opens_with_its_question_and_the_quick_start
FAILED tests/test_selection_layout.py::test_every_question_is_a_heading_with_an_emoji_of_its_own
FAILED tests/test_selection_layout.py::test_the_phases_and_the_settings_are_two_groups
FAILED tests/test_selection_layout.py::test_a_contribution_says_why_there_is_no_surface_under_the_settings
FAILED tests/test_selection_layout.py::test_each_setting_states_its_default_before_its_rows
FAILED tests/test_selection_layout.py::test_every_explanation_is_collapsed_and_no_box_is
FAILED tests/test_selection_layout.py::test_only_the_protected_phases_read_as_always_runs
FAILED tests/test_selection_layout.py::test_the_comment_still_ends_with_the_marker_and_the_stamp
FAILED tests/test_channels_digest.py::test_collapsed_blocks_unfold_for_slack
9 failed, 48 passed in 0.53s
```

## T1–T6: green after the change

| Command | Outcome |
|---------|---------|
| `cd cli && uv run python -m pytest -q tests/test_selection_layout.py` | 11 passed |
| `cd cli && uv run python -m pytest -q` | 5520 passed, 1 skipped |
| `uv run ruff check cli hooks` | all checks passed |
| `uv run ruff format --check cli hooks` | all files formatted |
| `uv run pyright cli` | 0 errors |
| `uv run python scripts/validate_config.py` | both configs valid |
| `npx markdownlint-cli2` on the changed docs | 0 errors |

## T7: rendered evidence

[`checklist-before.md`](checklist-before.md) and [`checklist-after.md`](checklist-after.md)
are `_checklist_body` output for the shipped outer loop, with every section offered.

| Measure | Before | After |
|---------|--------|-------|
| Words in total | 989 | 1,176 |
| Words visible before any click | 989 | 554 |
| Headings | 0 | 12 |
| Collapsed explanations | 0 | 9 |

## A flaky test that is not this change's

An earlier full run had one failure in `tests/test_control_integration.py`, which passed
when re-run. Run 15 times on base `26e4104` without this change, the file failed 8
times, in `test_a_dispatcher_without_an_opener_opens_nothing` (6) and
`test_a_start_opens_the_conversation_once_before_the_checkout` (2). Both wait on a
spawn thread with a timeout and touch nothing this change does. It is left for its own
ticket.
