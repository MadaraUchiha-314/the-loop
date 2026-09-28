---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#426"
---

# Verification: work-item mode launches Claude Code without its question menu

> The `verification` node's captured output, one section per row of
> [`testing-plan.md`](../testing-plan.md). Environment: Python 3.11, `uv` 0.12.19,
> `uv sync` against the committed `uv.lock`; Claude Code 2.1.283 and tmux for the
> manual rows.

## Verification results

| Row | Command | Outcome |
|-----|---------|---------|
| T8 | the real `claude` CLI, both spellings, before any code | space form turns the prompt into deny rules; `=` form runs it; space form then `=` form runs it |
| T7 | the five test modules on the unfixed source (tests kept, source stashed) | **20 failed**, 225 passed. Every new work-item-mode case fails; the two `cli`-mode cases pass, as they must (they pin unchanged behaviour) |
| T1–T5 | `tests/test_tmux_runner.py`, `test_interaction.py`, `test_tmux_runner_integration.py`, `test_interaction_integration.py`, `test_sessions_restart_integration.py` | **245 passed** |
| T9 | real interactive TUI in tmux | **not run**: the TUI stops at its OAuth login screen in this environment (see below) |
| T9b | the real `claude` CLI, deny semantics on a tool present in `-p` mode | `Bash` is `AVAILABLE` without the flag, `ABSENT` with `--disallowedTools=Bash`, and `ABSENT` with the ticket's space form followed by the `=` token, with the prompt still answered |
| T10 | `cd cli && uv run python -m pytest -q` (CI's command) | **4706 passed, 1 skipped** in 187.64s |
| T11 | `ruff format --check`, `ruff check`, `pyright cli`, `scripts/validate_config.py`, `markdownlint-cli2 "**/*.md"` | all green (see § T11) |

## T8: the real CLI's parsing, before the fix

```text
$ claude --help | grep -A1 disallowedTools
  --disallowedTools, --disallowed-tools <tools...>
      Comma or space-separated list of tool names to deny (e.g. "Bash(git *)
$ claude -p --disallowedTools AskUserQuestion
Error: Input must be provided either through stdin or as a prompt argument when using --print
$ claude -p --disallowedTools AskUserQuestion "Reply with the single word PONG"
Permission deny rule "Reply" matches no known tool — check for typos.
Permission deny rule "with" matches no known tool — check for typos.
Permission deny rule "the" matches no known tool — check for typos.
Permission deny rule "single" matches no known tool — check for typos.
Permission deny rule "word" matches no known tool — check for typos.
$ claude -p --disallowedTools=AskUserQuestion "Reply with the single word PONG"
PONG
$ claude -p --disallowedTools AskUserQuestion --disallowedTools=AskUserQuestion "Reply with the single word PONG"
PONG
```

The third command is the ticket's workaround, `harnesses[].args: [--disallowedTools,
AskUserQuestion]`, in the position the-loop puts it: right before the prompt. The prompt
becomes deny rules. The fifth is the same config with this fix applied.

## T9b: the `=` form really denies

`AskUserQuestion` is absent from `-p` mode whatever the flags, so the deny half is shown
on a tool that is present there.

```text
$ Q='Is a tool named Bash available to you right now (including deferred tools)? Reply with exactly one word: AVAILABLE or ABSENT.'
$ claude -p "$Q"
AVAILABLE
$ claude -p --disallowedTools=Bash "$Q"
ABSENT
$ claude -p --disallowedTools Bash --disallowedTools=AskUserQuestion "$Q"
ABSENT
```

The last line shows that the two occurrences add up (both denies apply), and that the
`=` token closes the operator's variadic flag, so the prompt arrives intact.

## T9: why the TUI row did not run

Two sessions were launched in tmux with the argv the adapter builds:
`claude --session-id <uuid> [--disallowedTools=AskUserQuestion] "<the ticket's prompt>"`.
Both stopped at Claude Code's first-run screens, and then at its login method and OAuth
URL. This environment authenticates the CLI for `-p` only, so no interactive session can
start. The row stays unticked. To close it on a logged-in machine:

```console
$ tmux new-session -d -s t426 -- claude --session-id "$(uuidgen)" \
    --disallowedTools=AskUserQuestion \
    "Ask me a multiple-choice question using your AskUserQuestion tool: blue-green or canary? Do not decide yourself."
$ sleep 30; tmux capture-pane -p -t t426 | grep -c 'Enter to select'   # expect 0
```

The reporter ran the treated half of this on Claude Code 2.1.281 and quoted the result
in the ticket: the agent reports that no `AskUserQuestion` tool exists, asks in text,
and completes its turn.

## T7: negative control

```text
FAILED tests/test_tmux_runner.py::TestUnattendedArgv::test_an_unattended_spawn_denies_the_question_tool_before_the_prompt
FAILED tests/test_tmux_runner.py::TestUnattendedArgv::test_an_unattended_resume_denies_it_too
FAILED tests/test_tmux_runner.py::TestUnattendedArgv::test_the_deny_follows_the_operators_own_arguments
FAILED tests/test_tmux_runner.py::TestUnattendedArgv::test_the_tickets_variadic_workaround_no_longer_eats_the_prompt
FAILED tests/test_tmux_runner.py::TestUnattendedArgv::test_the_token_is_one_word_so_it_takes_exactly_one_value
FAILED tests/test_tmux_runner.py::TestUnattendedArgv::test_an_attended_adapter_is_launched_exactly_as_before
FAILED tests/test_tmux_runner.py::TestUnattendedArgv::test_an_adapter_is_attended_until_told_otherwise
FAILED tests/test_tmux_runner.py::TestUnattendedArgv::test_with_unattended_keeps_everything_else
FAILED tests/test_tmux_runner.py::TestUnattendedArgv::test_with_unattended_returns_self_when_nothing_changes
FAILED tests/test_tmux_runner.py::TestUnattendedArgv::test_a_work_items_model_keeps_the_deny
FAILED tests/test_tmux_runner.py::TestUnattendedArgv::test_a_critics_one_shot_run_is_untouched
FAILED tests/test_tmux_runner.py::TestUnattendedArgv::test_cursor_has_nothing_to_deny
FAILED tests/test_interaction.py::test_only_cli_mode_has_someone_at_the_pane[data0-True]
FAILED tests/test_interaction.py::test_only_cli_mode_has_someone_at_the_pane[data1-True]
FAILED tests/test_interaction.py::test_only_cli_mode_has_someone_at_the_pane[data2-False]
FAILED tests/test_interaction.py::test_only_cli_mode_has_someone_at_the_pane[data3-True]
FAILED tests/test_tmux_runner_integration.py::test_a_work_item_mode_spawn_cannot_open_the_question_menu
FAILED tests/test_tmux_runner_integration.py::test_a_resumed_work_item_session_is_denied_the_menu_too
FAILED tests/test_interaction_integration.py::test_a_reload_moves_the_question_menu_with_the_mode
FAILED tests/test_sessions_restart_integration.py::TestQuestionMenu::test_the_default_mode_relaunches_without_the_menu
20 failed, 225 passed in 5.57s
```

Several unit tests fail on the missing `with_unattended` and `unattended` attributes
rather than on the argv. They still pin the argv once the API exists. The four
integration cases fail on the argv itself.

## T11: static checks

```text
$ uv run ruff format --check cli hooks
359 files already formatted
$ uv run ruff check cli hooks
All checks passed!
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
```
