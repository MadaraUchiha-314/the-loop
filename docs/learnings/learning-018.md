# Learning 018: Anchor a command grammar instead of teaching it markdown

- **Date:** 2026-10-23
- **Source:** user-feedback (the author's comment on issue-498)
- **Work item:** issue-498 (follows [learning-011](learning-011.md))

## What happened

Learning-011 planned to strip inline code and fenced blocks before the control grammar
ran, so a keyword quoted in a review comment would not count. On the ticket the author
proposed a simpler rule: a keyword counts only at the start of the message. That rule
covers every case the stripper was meant to cover — inline code, a fence, a `>` quote, a
list item and plain prose all put something other than the keyword first — without the
parser understanding any markdown.

## Learning

When untrusted text can trigger an action, constrain **where** the trigger may sit
before reaching for a parser that decides **what** the text means. An anchor is one regex
flag and is easy to reason about; a half-markdown parser is neither. And a body the
grammar refuses to act on is still something a person said: route it as conversation,
never settle it unread.

## Action

- issue-498: `parse_command` matches a keyword only at the start of the body, or at the
  start of a later line of a body that already opens with one; two different commands
  execute neither and the comment is routed as conversation (`control-ambiguous` is no
  longer a settled outcome).
