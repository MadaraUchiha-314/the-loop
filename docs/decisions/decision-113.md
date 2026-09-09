# Decision 113: a closed work item is stamped `ended` on its portable record and demoted, never deleted; `graph` stays

- **Status:** proposed
- **Date:** 2026-09-09
- **Work item:** [issue-329](https://github.com/MadaraUchiha-314/the-loop/issues/329)
- **Deciders:** the-loop (design); MadaraUchiha-314 (owner, at the PR)
- **Refines:** decision-046 (one portable record per work item, sections by portability); the issue-186 rule that cleanup keeps the portable half

## Context

Closed work items stayed on the control plane, mostly under *Needs you*, because nothing
on any surface said an item had ended. The ticket's own analysis found five independent
causes and proposed two families of fix: **record and demote** (stamp the record, teach the
board), or **converge to deletion** (clear the `graph` section so an emptied record is
removed). Three facts decided between them:

1. The closed **session record** stays in the registry and puts a row on the board
   through `/api/v1/sessions` whatever happens to the portable record — so deleting the
   record retires nothing on the machine that ran the item.
2. The `graph` section has a live reader after closure: `Dispatcher._tmux_for` reads the
   frozen `sessionPerPr` for every pull-request event, and a reopened item resumes from
   the checkout's `graph-state.json` with the portable copy as its only daemon-side view.
3. The record is the tracking that outlives the machine (issue-186, `cleanup.py`); a
   record that vanishes on closure loses the one fact — *it ended, when, by whom* — that a
   second machine or a later reader most wants.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **`ended` is a fifth portable section** — `{state, kind, reason, at, source, actor}` — written by the dispatcher's closed branch for every closing ref the-loop tracks, with or without a session. A record carrying only `ended` is kept. | One writer on the one close path both ingresses share; the fact is true on any machine, so it travels with `control` and `graph`. Keeping the record is what lets the board on any machine demote the row instead of guessing from a closed session record. |
| D2 | **`graph` is not cleared on closure.** | Its reader survives closure (fact 2); the ticket's "converge to deletion" was a means to retire the row, and D1 retires it directly. Reset still clears everything; cleanup still clears nothing portable. |
| D3 | **Both attention surfaces read the stamp** and suppress the stale signals — the open question, the parked gate, the blocked node, the armed-without-session — rather than emitting synthetic events to close them. | The event log stays a record of what happened; a synthetic `reply_sent` would be a lie in the log to fix a lie on the board. The two surfaces already share one open/answered rule by cross-reference; the ended rule joins it. |
| D4 | **Closure reconciliation walks everything the machine tracks** — every session record and every record with `control`, `graph` or `collaborators` — and skips stamped records. Poll-only records are excluded. | The active-sessions rule was exactly the gap: paused, exited and never-here items never learned they ended. Stamped records make the widened set cheap after one cycle; poll-only records would cost a provider call per unlabelled open item per cycle and put no urgent flag on the board. |
| D5 | **A polled closure names the closer** (`closed_by.login`) as the synthesized event's `sender`, and the cleanup actor gate is unchanged. | Attribution with the same provenance a webhook's `sender` has, judged by the same rule: an authorized closer's cleanup now runs on a polling deployment; anyone else's is deferred exactly as before. Relaxing the gate for provider-verified closures was the ticket's other option; it would let an unlisted login with write access destroy an operator's checkout by closing a ticket. |
| D6 | **A reopen clears the stamp** — from a `reopened` event, and from any listing that carries the item. | A stamp that outlives the closure would be the mirror of the bug being fixed. The listing rule also bounds a forged or stale stamp on a tracked repository to one poll cycle. |

## Consequences

**Good.** *Needs you* converges to empty; a closed item reads *Shipped* (merged, or an
issue closed) or *Idle* (a pull request closed unmerged) on every machine that carries the
record; the deferred-cleanup case on polling deployments shrinks to closures GitHub cannot
attribute or that an unlisted login performed; the record now says when and how an item
ended, which a retention window could later read.

**Costs, accepted.** `portable/` grows by one small section per closed item and never
shrinks on its own (reset is the remover, as it always was); the first poll cycle after
upgrade asks the provider about every tracked-but-unlisted item once; the *Shipped* group
grows until a retention rule exists (out of scope here, and now possible).

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Clear `graph` on closure so records converge to deletion | Retires nothing where a closed session record remains (fact 1); loses the closure fact; removes a section a reader still needs (fact 2) |
| Delete the record **and** the closed session record on closure | Discards the transcript handle `keepSessionOnClose` exists to keep; two removals to fix a display problem |
| Emit a synthetic `session.reply_sent` on closure | Falsifies the event log; the question was never answered |
| Relax `_cleanup_after_close` for provider-verified closures with no actor | Lets an unattributable event destroy uncommitted work — the exact trade issue-186 refused |
| Reconcile every portable record including poll-only ones | One provider call per unlabelled open item per cycle, for rows that carry no urgent flag |
| Reconcile only records with `control` (armed items) | Misses items whose arming was cleared by a stop, and items known only through a frozen graph or a roster |
