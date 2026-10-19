# Learning 011: A keyword mentioned in prose is not a command

- **Date:** 2026-10-19
- **Source:** user-feedback (the author's "why was the previous comment not processed?")
- **Work item:** issue-496 (fix tracked as issue-498)

## What happened

At `design-approval` the author wrote a review comment that discussed how the-loop's own
commands interact: "one user … has done `the-loop start` … other user … has done
`the-loop review`". `control.parse_command` matches every configured keyword as a whole
token anywhere in the body, found `start` and `review`, and returned `ambiguous`. The
dispatcher settled the comment as `control-ambiguous` with `will_retry: false`, so the
session never received it and the author had to ask why. One minute later the author's
follow-up reached the session only because it named no keyword.

## Learning

The ambiguity rule protects the-loop from acting on a body that says two conflicting
things. It must not make the body disappear: a review comment on a harness that is itself
about the harness will mention commands, and the gate exists to collect exactly that
comment. Mentions inside backticks are never commands, and an ambiguous body is still
conversation for the session that is waiting on it.

## Action

- issue-498: strip code spans and fenced blocks before the control grammar runs;
  forward an ambiguous body to the live session as conversation while recording
  `control.ambiguous` and acting on no command.
- Until then, replies to the gate's review request that discuss commands are safest
  without the bare keywords.
