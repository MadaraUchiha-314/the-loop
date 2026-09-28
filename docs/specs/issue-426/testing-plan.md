---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#426"
status: in-review            # draft | in-review | approved — locked with bugfix.md
approvedBy: []
overrides: {}
riskTier: 3
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: work-item mode launches Claude Code without its question menu

> Derived from [`bugfix.md`](bugfix.md) and [`design.md`](design.md). Planned at
> `test-planning`, results recorded at `verification`. See
> [`evidence/verification.md`](evidence/verification.md).

## What "proved" means here

Three things have to hold.

- The token reaches every launch of a work item's session in `work-item` mode, and no
  launch in `cli` mode.
- The prompt stays the positional argument, including after the ticket's variadic
  workaround.
- Nothing else moves: the recorded arguments, standing sessions, critics and cursor.

The parsing claim is about a real binary, so it is proved against the real Claude Code
CLI, not a stub.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (adapter argv) | yes | unattended spawn and resume argv end `…, --disallowedTools=AskUserQuestion, <prompt>`; attended argv unchanged; after operator args; after a trailing `--disallowedTools AskUserQuestion` the prompt is still last; `with_unattended` keeps args/trust/binary, returns `self` when unchanged; `with_args` keeps the flag; one-shot argv unaffected; cursor unaffected (R1.1, R1.3, R1.4, R2.1, R3.2, R3.3) | `tests/test_tmux_runner.py` |
| T2 | Unit (mode) | yes | `unattended` is true for `work-item`, false for `cli`, true for an undeclared value (R2.2) | `tests/test_interaction.py` |
| T3 | Integration (dispatcher spawn) | yes | real dispatcher over the stub tmux: default mode spawn carries the token immediately before the prompt; `cli` spawn does not; recorded `harness_args` exclude it (R1.1, R2.1, R2.4) | `tests/test_tmux_runner_integration.py` |
| T4 | Integration (dispatcher respawn) | yes | a dead session is resumed with the token; a reload to `cli` drops it on the next launch (R1.2, R2.3) | `tests/test_tmux_runner_integration.py` |
| T5 | Integration (`sessions restart`) | yes | the relaunch argv carries the token by default and not under `cli` (R1.2) | `tests/test_sessions_restart_integration.py` |
| T6 | Integration (standing session) | yes | existing standing-session tests stay green; `core.standing` never calls `with_unattended`, so its adapter keeps the attended default T1 pins (R3.1) | `tests/test_standing_integration.py` (inside T10) |
| T7 | Negative control | yes | T1, T3–T5 on the unfixed source (tests kept, source stashed): the new cases fail | the modules above |
| T8 | Manual (real CLI, parsing) | yes | on Claude Code 2.1.283: space form swallows the prompt; `=` form runs it; space form followed by `=` form runs it | a scratch directory |
| T9 | Manual (real TUI in tmux) | yes | a real interactive Claude Code session in tmux, launched with the argv the adapter builds, asked to use `AskUserQuestion`: no `Enter to select` menu and the turn completes; the same without the flag renders the menu (control) | tmux on the dev box |
| T9b | Manual (real CLI, deny semantics) | yes | substitute for T9's deny half where the TUI cannot run: with a tool that *is* present in `-p` mode (`Bash`), `--disallowedTools=Bash` removes it, and `--disallowedTools Bash --disallowedTools=AskUserQuestion "<prompt>"` removes it while the prompt still runs | a scratch directory |
| T10 | Regression (full suite) | yes | green from `cli/`, CI's command | `make test` |
| T11 | Static (lint, format, types, markdown, config) | yes | green | `make lint format-check typecheck validate` |
| T12 | Performance | n/a: one tuple concatenation and at most one shallow copy per launch | | |
| T13 | UI / visual | n/a: nothing rendered by the UI changes | | |
| T14 | Contract (OpenAPI) | n/a: no route, request or response changes | | |

## Scenarios & requirement trace

| Requirement | Rows |
|---|---|
| R1.1–R1.4 | T1, T3, T4, T5, T8, T9, T9b |
| R2.1–R2.4 | T1, T2, T3, T4 |
| R3.1–R3.3 | T1, T6 |

## Verification environment

- Python 3.11, `uv`, dependencies from `uv sync` against the committed `uv.lock`.
- Claude Code 2.1.283 and tmux 3.x on the dev box, for T8, T9 and T9b only.

## Activities

- [x] T8 — real CLI parsing, before writing code
- [x] T7 — negative control
- [x] T1–T5 — targeted modules
- [ ] T9 — real TUI in tmux. **Not run:** this environment's Claude Code
      authenticates only in `-p` mode, and the interactive TUI stops at its OAuth
      login screen. The reporter ran the treated half on a real TUI (Claude Code
      2.1.281) and recorded it in the ticket. T8 and T9b prove the parsing and the deny
      against the real binary. A reviewer with a logged-in TUI can close this row with
      the command in `evidence/verification.md` § T9.
- [x] T9b — real CLI deny semantics
- [x] T10 — full suite from `cli/`
- [x] T11 — static checks
