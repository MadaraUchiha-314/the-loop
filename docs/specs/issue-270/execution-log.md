---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#270"
phase: requirements-definition   # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress              # in-progress | complete
---

# Execution Log: a comment made before `the-loop start` is never delivered, and nothing says so

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| not-started | 2026-08-18 | — | ticket #270, split out of #269 § *Related casualty* |
| phase-selection | 2026-08-18 | — | see Deviations: the loop was run by hand in a cloud session, not by a daemon |
| requirements-definition | 2026-08-18 | pending | `bugfix.md` |

## Pull requests

| Repository | PR | Loop state | Status |
|---|---|---|---|
| MadaraUchiha-314/the-loop | (this branch) | outer loop only — one repository, one delivery | open |

## Progress entries

### 2026-08-18 — the product decision was already made; the ticket names its two consequences

The ticket is explicitly a **product decision** ("a call for the owner, not for the loop"),
and the owner made it in a one-word comment: **Option-3** — the session re-reads the thread,
so the *content* of a pre-start comment is not lost; only the delivery accounting is wrong.
Option 3's own text carries the two things that then have to happen: *"it should be written
down, and `commentAttempts` should stop implying a pending retry."* This work item is those
two, and nothing else — no replay (option 1), no durable refusal marker (option 2).

### 2026-08-18 — reading the accounting turned up a worse tail than the ticket describes

The ticket says the comment "stays at `commentAttempts: 1` forever". True while the daemon
lives. Two things happen after that, and both are worse:

1. The dedup mark is a **process-local LRU**. On a restart — or after `dedupCacheSize`
   deliveries — `delivery_status` flips from `inflight` to `unhandled`, the poller spends
   attempts 2 and 3, and emits `poll.comment_failed` at error level *plus* a comment on the
   ticket telling the human their comment never reached the session after three attempts.
   Nothing was attempted; nothing failed.
2. That give-up is written into `gaveUp` with the CLI version, and `rearm_gave_up_comments`
   (issue-146) un-resolves anything a **different** version abandoned. So the first upgrade
   after the false give-up re-forwards the comment — **delivered late** if the item has been
   started by then. Today's behaviour is not "never replayed"; it is replay-on-upgrade,
   which is option 1's semantics arrived at by accident on a schedule nobody chose.

Recorded because it changes what "stop implying a pending retry" has to mean: the comment must
be **resolved**, and resolved as *baselined*, not as *given up*.
