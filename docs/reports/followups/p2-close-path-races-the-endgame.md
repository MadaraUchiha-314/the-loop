# bug: the close path ends the session while it is composing its completion summary

From [`docs/reports/e2e-slack-test-2026-09-20-run-3.md`](../e2e-slack-test-2026-09-20-run-3.md)
(P2), the live validation run of the PR #402 fixes on the-loop 19.8.3.

## Seen

The approval's merge carried `Closes #5`; GitHub closed the issue at once; the
close-poller fired; `close_session` SIGTERM'd the session (pane status 143) and removed
the checkout while the agent was writing its completion summary. The summary never
reached the room or the ticket. `session.autoclosed` logged `merged: false` seconds after
the delivering PR merged.

## Root cause

An `issue-closed` closure tore the session down synchronously — harness, registry
record, checkout, stamp, cleanup — whatever the session was doing. Run 2 won the race
(the session posted before the poll cycle); run 3 lost it. The `merged` field was
`reason == "pr-merged"`, which an issue closure can never satisfy.

## Fixed (issue-405)

- A closure that reaches a **live** session standing on the graph's **terminal node**
  (its exit not yet recorded — `finish-tasks` in progress) is **held**:
  `session.closing`, nothing torn down. The session's `the-loop graph complete <id>`
  claim ends the hold at once; `routing.tmux.finishGraceSeconds` (default 300, `0` = the
  old behaviour) ends it regardless. `session.autoclosed` then carries `waited_seconds`
  and `finished`. A pointer anywhere else, a dead pane or an unreadable graph closes
  immediately as before; a reopen during the hold cancels it; the poller leaves a held
  item alone.
- `session.autoclosed merged` is `true` when a pull request recorded on the work item
  merged.
- `finish-tasks` and the skill state the endgame order: post the summary, claim
  `graph complete`, then close the ticket if it is still open.
