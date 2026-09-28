---
type: bugfix
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#426"
status: in-review            # draft | in-review | approved — tier 3: a human approves the PR
approvedBy: []
severity: high
collaborators: [engineer]
overrides: {}
riskTier: 3                  # changes the argv of every Claude session the daemon launches in work-item mode; no schema, state-file or grant change
---

<!-- Authored per the the-loop:writing skill. -->

# Bugfix spec: a work-item session freezes on Claude Code's interactive question menu

> Phase 1 of 4 (bugfix → design → testing plan → tasks). Source:
> [issue-426](https://github.com/MadaraUchiha-314/the-loop/issues/426).

## Summary

In `routing.interaction.mode: work-item` (the default), the prompt tells the session
that nobody is watching its terminal and that every question goes on the work item
through `the-loop ask`. Nothing enforces that. Claude Code's `AskUserQuestion` tool
stays in the session's toolset. When the model reaches for it, the session renders a
multiple-choice menu in its tmux pane and blocks on a keypress.

- The menu emits no the-loop event, so nothing reaches the ticket or a channel.
- Every later message is pasted into a pane that is waiting on a menu, so it is
  recorded as delivered and never read.
- The work item looks parked and healthy until somebody attaches to tmux by hand.

The reporter lost about an hour to this twice in one evening.

**The fix.** In `work-item` mode, the daemon launches Claude Code with
`--disallowedTools=AskUserQuestion`. The tool is gone, so the model asks in text or
through `the-loop ask`, and its turn ends. `cli` mode, where a human sits in the pane,
keeps the tool.

**The spelling matters.** Written with an `=`, the flag takes exactly one value.
`--disallowedTools` is variadic: the space-separated form the ticket suggests,
`--disallowedTools AskUserQuestion`, also swallows every word after it that does not
start with `-`. In the-loop's argv the next word is the spawn prompt, so the prompt
turns into deny rules and the session starts with no prompt at all. See
[Reproduction](#steps-to-reproduce) step 5. The ticket's workaround has exactly this
defect, and this fix repairs a config that still carries it (R1.4).

## Steps to reproduce

1. Configure a Claude harness and start a work item, so a session is spawned in tmux
   in `interaction.mode: work-item`.
2. Send the session a genuinely ambiguous instruction.
3. The agent opens an `AskUserQuestion` menu in its pane and blocks:

   ```text
   ❯ 1. <option one> (Recommended)
     2. <option two>
     3. Type something.
     4. Chat about this

   Enter to select · ↑/↓ to navigate · Esc to cancel
   ```

4. No event is emitted and nothing reaches the ticket or a channel. Further operator
   messages log `channel.reply_received` → `dispatch.succeeded` and are never read.
5. The ticket's workaround, `args: [--disallowedTools, AskUserQuestion]`, puts the flag
   right before the positional prompt. On Claude Code 2.1.283:

   ```console
   $ claude -p --disallowedTools AskUserQuestion "Reply with the single word PONG"
   Permission deny rule "Reply" matches no known tool — check for typos.
   Permission deny rule "with" matches no known tool — check for typos.
   …
   $ claude -p --disallowedTools=AskUserQuestion "Reply with the single word PONG"
   PONG
   ```

## Expected vs actual

| | Expected | Actual |
|---|---|---|
| a Claude session spawned or resumed in `work-item` mode | launched without `AskUserQuestion`; a question ends the turn | the tool is available; a question can freeze the pane indefinitely |
| the same in `cli` mode | the tool is available (a human answers in the pane) | same (correct today) |
| an operator config ending `--disallowedTools AskUserQuestion` | the session gets its prompt | the prompt becomes deny rules; the session boots with none |

## Root cause

`ClaudeCodeAdapter.interactive_argv` and `interactive_resume_argv`
(`cli/the_loop/harness/claude_code.py`) build
`[--session-id|--resume, <id>] + extra_args + [prompt]`. `extra_args` is the operator's
`harnesses[].args`, empty by default, and nothing on the spawn path reads the
interaction mode. The mode reaches the prompt (issue-134) and never the argv, so "never
block on an interactive prompt" is advice the runtime could enforce and does not.

## Requirements

### Requirement 1: a work-item-mode Claude session cannot open the question menu

1. WHEN the daemon spawns a Claude Code session for a work item and the resolved
   `routing.interaction.mode` is `work-item` THEN the argv SHALL carry
   `--disallowedTools=AskUserQuestion`.
2. The same SHALL hold for every other launch of a work item's session: a respawn that
   resumes the conversation, a fresh respawn, a pull request's own session, and
   `the-loop sessions restart`.
3. The flag SHALL be written as one `--disallowedTools=<tool>` token, placed after the
   operator's arguments and immediately before the positional prompt, so that it can
   never consume the prompt.
4. WHEN the operator's arguments end with a variadic flag and its values
   (`--disallowedTools AskUserQuestion`, the ticket's workaround) THEN the session SHALL
   still receive its prompt as the positional argument.

### Requirement 2: the mode is the switch

1. WHEN the resolved mode is `cli` THEN the argv SHALL be exactly what it was before this
   change.
2. An unrecognised mode already resolves to `work-item` (issue-134). It SHALL therefore
   deny the tool as well.
3. A reloaded mode SHALL apply from the next launch. A running session keeps the argv it
   was launched with.
4. The arguments the registry records for a session (`harness_args`) and the drift
   comparison built on them (issue-358) SHALL NOT change, so upgrading relaunches
   nothing.

### Requirement 3: nothing else changes

1. A standing session (issue-277) is not governed by the interaction mode and SHALL keep
   its argv.
2. A critic's one-shot run (`-p`) SHALL keep its argv.
3. The cursor-agent adapter has no such tool and SHALL be unchanged.

## Security considerations

- **This removes capability; it grants none.** The session loses one interactive tool.
  No permission is widened, and no new input, route, credential, file write or
  subprocess is added.
- **No untrusted data reaches the argv.** The new token is a constant. The mode that
  selects it is operator config, resolved by the existing fail-closed
  `InteractionConfig`.
- **Fail-closed direction.** A typo in the mode resolves to `work-item` and denies the
  tool. The worst case of a wrong deny is an agent that asks in text and waits, which is
  the directive's instruction anyway. The worst case of a wrong allow is the silent
  freeze this ticket reports.

## Out of scope

- **The ticket's option 3: an event for a session idle at a prompt.** Detecting a TUI
  that waits on a keypress means scraping the pane or watching the process, and every
  interactive tool of every harness would need its own detector. This fix removes the
  one known cause. The general detector is a separate work item.
- **A separate opt-out key.** The ticket asks for an opt-out "for operators who really
  do sit in the pane". Those operators already declare `interaction.mode: cli`, which
  keeps the tool. See [`design.md`](design.md) § Trade-offs.
- **Other harnesses.** cursor-agent cannot be tmux-hosted at all (issue-32).
