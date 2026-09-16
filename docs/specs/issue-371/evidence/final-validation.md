---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#371"
---

<!-- Authored per the the-loop:writing skill. -->

# Final validation: every comment the-loop finishes with says so on the comment

> The `verification` node's proof: every activity in `testing-plan.md` ticked, with the
> command, the outcome and the committed artifact.

## Results

| # | Command | Outcome | Artifact |
|---|---|---|---|
| T1 | `pytest cli/tests/test_reactions.py -k settled_outcome` | pass | `test_every_settled_outcome_is_classified_or_deliberately_silent` |
| T2 | `pytest cli/tests/test_reactions_integration.py -k grant_is_acknowledged` | pass — 🎉 on the comment, roster written, nothing delivered | `test_a_grant_is_acknowledged_on_the_comment_that_carried_it` |
| T3 | `pytest … -k executed_session_command` | pass — 🎉, session paused | `test_an_executed_session_command_is_acknowledged` |
| T4 | `pytest … -k refused_command` | pass — 😕, nothing spawned, outcome `control-rejected` | `test_a_refused_command_is_acknowledged_with_the_error_reaction` |
| T5 | `pytest … -k conflicting_keywords` | pass — 😕, outcome `control-ambiguous` | `test_conflicting_keywords_are_acknowledged_with_the_error_reaction` |
| T6 | `pytest … -k suppressed_comment` | pass — 👀 once, outcome `awaiting-start`, nothing spawned or delivered | `test_a_suppressed_comment_is_acknowledged_as_seen` |
| T7 | `pytest … -k out_of_scope` | pass — no `gh` invocation on either route | `test_an_out_of_scope_refusal_leaves_no_mark` |
| T8 | `pytest … -k silent_drops` | pass — policy drop and duplicate both silent | `test_the_silent_drops_stay_silent` |
| T9 | `pytest cli/tests/test_reactions_integration.py` (issue-84's four scenarios) | pass, unmodified | existing tests in the same file |
| T10 | `pytest … -k in_worker_settle` | pass — `_dispatch_one` posts nothing, outcome `session-paused` | `test_the_in_worker_settle_adds_no_reaction` |
| T11 | `pytest … -k disabled_reactions_silence_the_consumed_branch` | pass — roster written, no `gh` | `test_disabled_reactions_silence_the_consumed_branch_too` |
| T12 | `pytest cli/tests/test_reactions.py -k reactor_that_raises` | pass — settled outcome survives an exploding reactor | `test_a_reactor_that_raises_cannot_break_a_settle` |
| T13 | `pytest cli/tests/test_control.py cli/tests/test_routing.py cli/tests/test_control_integration.py` | pass, untouched | existing suites |
| T14 | review | done | `evidence/documentation.md` |
| T15 | review | no findings | `evidence/security-review.md` |
| T16 | n/a | not applicable — one bounded best-effort subprocess, analysed in `design.md` § "A known consequence" | — |
| T17 | n/a | not applicable — no UI surface | — |

## Gates

```text
make lint          → ruff: All checks passed! · markdownlint: 0 error(s) over 1178 files
make format-check  → 306 files already formatted
make typecheck     → pyright: 0 errors, 0 warnings
pytest -q cli      → 3760 passed, 1 skipped (11 new)
```

## Acceptance criteria

| AC | Proven by |
|----|-----------|
| AC1 | T2 |
| AC2 | T4 |
| AC3 | T5 |
| AC4 | T6 |
| AC5 | T7 |
| AC6 | T8 |
| AC7 | T9, T10 |
| AC8 | T11 |
