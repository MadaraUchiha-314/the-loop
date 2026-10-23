---
type: bugfix
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#498"
status: draft                # draft | in-review | approved
approvedBy: []
severity: medium             # low | medium | high | critical
riskTier: 4                  # control trust boundary; touches **/*schema* and .the-loop/** (description text only) — raised per the sensitive-path rule
collaborators: [engineer]
overrides: {}
---

# Bugfix spec: Control grammar drops a comment that mentions two keywords in prose

## Summary

A comment that only *mentions* the-loop's commands is read as two commands, declared
ambiguous, and settled unread: the session never sees it
([#498](https://github.com/MadaraUchiha-314/the-loop/issues/498), found on #496,
[learning-011](../../learnings/learning-011.md)).

The fix makes a command something a comment **opens with**, as the author asked on the
ticket ("make sure the control keyword is always in the starting of the message. If it's
in the middle, things won't be acted on"). Prose that mentions a keyword is then ordinary
conversation, and a body that still carries two different commands is forwarded to the
session as conversation instead of vanishing.

## Steps to reproduce

1. Arm a work item and start it, so a session is running.
2. As an authorized user, comment: ``one user has done `the-loop start` and the other has done `the-loop review` ``.
3. Read the event log and the session.

## Expected vs actual

- **Expected:** the comment reaches the session as conversation; no command runs.
- **Actual:** `control.parse_command` finds `start` and `review` anywhere in the body and
  returns `ambiguous`; the dispatcher emits `control.ambiguous` and settles the delivery
  as `control-ambiguous` (`will_retry: false`). The session never receives the comment.

## Root cause (confirmed)

Two rules combine:

1. `parse_command` (`cli/the_loop/control.py`) searches for each keyword **anywhere** in
   the body, including inside inline code and fenced blocks, so prose about the commands
   is read as commands.
2. `Dispatcher.handle` (`cli/the_loop/webhook/dispatcher.py`) treats an ambiguous result
   as *consumed*: it executes nothing **and forwards nothing**.

## Requirements

### Requirement 1 — A command is what a comment opens with

The control grammar recognises a keyword only at the start of the body. Everything after
the first line is the command's own text (its argument, a checklist), never a second
command by position alone.

#### Acceptance criteria (EARS)

1. WHEN a body's first non-whitespace text is a configured keyword (whole token,
   case-insensitive) THEN the parser SHALL return that command.
2. WHEN a configured keyword appears in a body anywhere other than at its start — later
   on the first line, inside inline code, inside a fenced block, inside a `>` quote, or on
   a later line of prose — THEN the parser SHALL NOT return a command for it.
3. WHEN a body opens with an argument-carrying command (`add-collaborator`,
   `remove-collaborator`, `add-channel`, `remove-channel`) and later lines also **begin**
   with the same keyword THEN the parser SHALL collect the arguments of every such line,
   as it does today.
4. WHEN a body opens with a keyword and a later line **begins** with a *different*
   keyword THEN the parser SHALL report the body as ambiguous (the `pause` / `resume`
   guard is kept for bodies that really issue two commands).
5. The rule SHALL hold for every surface that reads the grammar: GitHub and Jira comments
   (webhook and poll), and Slack messages once the bot's own mention is removed.
6. The fix SHALL include regression tests, failing before the fix, for the #496 comment
   and for each placement in criterion 2.

### Requirement 2 — An ambiguous body is conversation, not a dead letter

#### Acceptance criteria (EARS)

1. WHEN the parser reports a body as ambiguous THEN the dispatcher SHALL emit
   `control.ambiguous` (as today) AND SHALL act on none of its commands.
2. WHEN the parser reports a body as ambiguous THEN the dispatcher SHALL route the event
   exactly as it routes a comment that carries no command (scope, authorization, the
   paused / awaiting-start rules, delivery to the session), instead of settling it as
   `control-ambiguous`.
3. The fix SHALL include a regression test showing an ambiguous comment is enqueued for
   the live session.

### Requirement 3 — The rule is documented where the keywords are

#### Acceptance criteria (EARS)

1. `docs/capabilities/webhook-triggers.md` SHALL state the leading-keyword rule and the
   ambiguous-body behaviour beside the keyword list.
2. Code and doc text that says a keyword matches "anywhere" in a body SHALL be corrected.
3. `docs/learnings/` SHALL carry a learning entry for this fix (updating learning-011's
   action to what shipped).

## Security considerations

- **Untrusted actor / input.** Comment bodies are untrusted; only an authorized user's
  body reaches the parser at all (self-marker and `authorizedUsers` guards upstream, both
  unchanged).
- **Trust boundary.** The parser decides whether a body causes a *daemon action*. This fix
  **narrows** what it accepts: a keyword must lead the body. A body that used to execute
  a command because a keyword sat mid-prose now executes nothing — the fail-closed
  direction.
- **Abuse case: half a command executed.** A body that issues two different commands
  (each at the start of a line, criterion 1.4) still executes neither. Forwarding it as
  conversation (R2) gives the session text it could already have received from the same
  authorized author; it grants no action.
- **Abuse case: forwarding bypasses a gate.** R2.2 forwards through the *same* path as a
  command-free comment, so scope (issue-322), the paused and awaiting-start suppressions
  and the collaborator rules still apply. No new attack surface beyond what a plain
  comment already has.
- Returned values stay fixed-shape: the parser still returns only declared command
  constants and validated arguments, never body text.

## Out of scope

- The instance-address token (`instance:<name>`, `cli/the_loop/instance.py`) keeps its
  own grammar.
- `redact.defang_control_keywords` keeps defanging keywords anywhere — harmless and still
  useful for a composed body that might open with one.
- Stripping markdown generally: with the leading-keyword rule, a keyword in code or a
  quote is not at the start of the body, so no markdown parser is needed (this replaces
  the ticket's proposed fix 1).

## Open questions

None. The author's ticket comment settled the matching rule.
