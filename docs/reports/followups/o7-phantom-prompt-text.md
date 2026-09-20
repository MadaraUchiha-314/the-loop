# Investigate: unsent text appears in a session's tmux prompt that nobody submitted

**Kind:** investigation · **Source:** e2e Slack test 2026-09-19 (O7) · **Not fixed in issue-393**

## What was seen

Twice, right after the session asked a question and stopped, the tmux pane showed
a fully typed but **unsent** reply on the `❯` line — "Defaults are fine —
converged, go ahead", then "Approved, proceed to design." The daemon's event log
shows **no** delivery at those times. So either a person was attached to the pane
and typed it, or something is priming the prompt.

## Why it matters

An unsent line left in the prompt is concatenated with the next reply the daemon
*does* deliver — so a phantom "Approved, proceed to design." sitting in the buffer
could ride along with, and corrupt, the next real message pasted into the session.
That is a correctness hazard for the whole deliver-into-tmux path, not just a
cosmetic oddity.

## What to do

This is an **investigation**, not a known fix:
1. Reproduce — determine whether the text comes from a human attaching to the
   pane, from the-loop's own delivery path, or from the harness/tmux itself.
2. If the-loop primes the prompt anywhere, stop it, or clear the input line before
   each delivery so a leftover cannot concatenate.
3. Confirm the deliver path (`paste-buffer` + submit) cannot leave a partial line
   behind on a failed or interrupted delivery.

## Acceptance

- The source of the phantom text is identified, and either eliminated or shown to
  be a harmless external cause (a human at the pane); the deliver path is shown
  not to concatenate a leftover line with the next delivered reply.
