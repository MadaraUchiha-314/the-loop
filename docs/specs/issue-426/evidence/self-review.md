---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#426"
---

# Self-review: work-item mode launches Claude Code without its question menu

> The self/critic review before requesting human review
> ([`reference/reviewing.md`](../../../../skills/the-loop/reference/reviewing.md)). I read
> the branch diff adversarially, asking what would make CI or a reviewer reject it, and
> which launch could still reach a pane with the menu.

## Review cycles

### Cycle 1: the ticket's fix against the real binary

1. **Found: the ticket's suggested spelling breaks the session.** `--disallowedTools
   <tools...>` is variadic. Placed where the-loop puts operator arguments, right before
   the positional prompt, it consumes the prompt as deny rules (`verification.md` § T8).
   The ticket's own workaround therefore boots every session with no prompt. The fix
   uses the one-token `=` form, and the bugfix states the hazard as R1.3/R1.4.
2. **The opt-out.** The ticket asks for option 1 "with an opt-out". `cli` mode already
   means a human answers in the pane, so I made the mode the switch rather than adding
   a key that could contradict the prompt (`design.md` § Trade-offs).

### Cycle 2: the diff

1. **Every launch seam.** `grep` for `interactive_argv`, `interactive_resume_argv`,
   `spawn(`, `spawn_in(` and `respawn_in(`: the four dispatcher spawns resolve their
   adapter through `_adapter_for`, `sessions restart` through `_restart_adapter`, and
   `core.standing` is the only other caller, excluded on purpose (R3.1).
2. **Found and fixed: a stale docstring.** `_adapter_for` said the no-choice path
   "returns the shared adapter unchanged and allocates nothing". It now returns a copy
   when unattended. The sentence now states what R6.1 actually promises: no model or
   effort is applied.
3. **Drift.** `_choice_drifted` compares `extra_args`, which the token never enters,
   so upgrading relaunches nothing (pinned by the spawn test's `harness_args == []`).
4. **Aliasing.** `with_unattended` uses `copy.copy`, so the clone shares the
   `extra_args` list with the shared adapter. Nothing mutates it in place:
   `_launch_args` builds a new list, and `with_args` assigns a new one.

## Checked and left as is

- **A duplicate deny when the operator already carries the workaround.** Harmless
  (T9b), and de-duplicating would bring back the swallowed prompt.
- **`cli` mode with a trailing variadic flag in `harnesses[].args`.** Still swallows the
  prompt. That is the operator's own argument list; it is now documented in
  `harnesses-options.md` rather than rewritten, since the-loop never reorders or
  rewrites what an operator declared.
- **T9 (a real TUI).** Could not run here; see `verification.md` § T9.

## Critic review

Pending: a critic on a different model is reviewing the branch; its findings and my
replies are recorded here in the next commit.
