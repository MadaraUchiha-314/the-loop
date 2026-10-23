---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#498"
---

# Final validation: a control keyword must open the comment; an ambiguous body is conversation

> The `evidence` node's proof: the acceptance criteria of `bugfix.md`, each mapped to how
> the executed `testing-plan.md` proved it. Summarised from the plan's Verification
> results. The full suite was rerun after the critic fix: **6788 passed**, lint, format,
> type check and validate clean.

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| R1.1 — a body opening with a keyword is that command | T1 whole-token cases, leading whitespace included | [unit.md](unit.md) |
| R1.2 — a keyword anywhere else is not a command | T1: the #496 body, mid-line, backticks, bold, parentheses, quote, fence, indented, list item, a later line of prose (13 cases, red on the pre-fix parser); T2 `test_a_comment_discussing_two_commands_in_prose_reaches_the_session` | [unit.md](unit.md), [integration.md](integration.md) |
| R1.3 — argument lines repeating the command all count | T1 `test_several_logins_and_a_repeated_keyword_all_count` (and a mid-line mention ignored) | [unit.md](unit.md) |
| R1.4 — a different command opening a later line is ambiguous | T1 `test_a_different_command_opening_a_later_line_is_ambiguous` and the per-command suites | [unit.md](unit.md) |
| R1.5 — every surface reads the rule | T12: webhook and poll suites; the Slack relay now opens with the person's words (`test_bus*`, `test_channels*`, `test_selection_control`); the phase-selection gate reads the same grammar (critic fix) | [lint-and-typecheck.md](lint-and-typecheck.md), [critic-review.md](critic-review.md) |
| R1.6 — regression tests fail before the fix | T1 red check against `13c915d5` | [unit.md](unit.md) |
| R2.1–R2.3 — ambiguous: `control.ambiguous` emitted, nothing executed, routed as a plain comment and delivered | T2 `test_an_ambiguous_comment_reaches_the_live_session_and_executes_nothing`, `test_an_ambiguous_comment_does_nothing_at_all`, reactions scenario | [integration.md](integration.md) |
| Security: forwarding bypasses no gate | T8 paused-session scenario; gate tests in `test_selection_choices.py`; security review | [integration.md](integration.md), [security-review.md](security-review.md) |
| R3.1–R3.3 — documented beside the keywords; "anywhere" wording corrected; learning entry | `webhook-triggers.md` keyword bullet + changelog row, `channels.md`, `process-graph.md`, both schema copies, `redact.py`; `learning-018.md` (learning-011's action updated) | the diff |
