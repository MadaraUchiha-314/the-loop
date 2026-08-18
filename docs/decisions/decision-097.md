# Decision 097: a refused delivery is settled, not pending — and the thread is the replay

- **Status:** proposed
- **Date:** 2026-08-18
- **Work item:** [issue-270](https://github.com/MadaraUchiha-314/the-loop/issues/270)
- **Deciders:** MadaraUchiha-314 (owner — "Option-3" on the ticket), the-loop (proposal)
- **Refines:** [decision-040](decision-040.md) (execution control: the label is necessary,
  not sufficient), [decision-095](decision-095.md) (which left this out of scope on purpose)

## Context

A comment posted before an authorized `the-loop start` is refused with
`dispatch.dropped reason: awaiting-start`, and its delivery id is deliberately **kept** in
the dedup cache — releasing it would have GitHub redeliver, and the poller re-forward, every
comment on every labelled work item nobody has started. That refusal is right. What it left
behind was not.

The dedup mark has only ever meant "seen". The poll path reads it through
`Dispatcher.delivery_status`, whose three answers are *done*, *inflight* and *unhandled* — so
a deliberate refusal came back as **inflight**, and the work item's ledger recorded the
comment as `commentAttempts: 1`, forever. The same entry that means "we are still trying" now
meant "we decided not to".

Then it got worse, in two steps the ticket did not describe:

1. The mark is a **process-local LRU**. On a restart (or after `dedupCacheSize` deliveries)
   the answer flips to *unhandled*, the poller spends attempts 2 and 3, emits
   `poll.comment_failed` at error level and — since issue-240 — posts a comment on the ticket
   telling the human their comment never reached the session after three attempts. Nothing
   was attempted; nothing failed.
2. That give-up is written to `gaveUp` with the CLI version, and `rearm_gave_up_comments`
   (issue-146) un-resolves anything a *different* version abandoned. The first upgrade after
   the false give-up therefore **re-forwards** the comment — delivered late if the item has
   been started by then. Today's behaviour was not "never replayed"; it was
   replay-on-upgrade.

The ticket asked for a product decision between replaying pre-start comments, recording a
durable "gave up" marker, or neither. The owner chose **neither**: the session re-reads the
thread. That choice comes with the two consequences its own text names — write it down, and
stop `commentAttempts` implying a pending retry.

## Decision

| Sub-decision | What was chosen | Why |
|---|---|---|
| D1 | **Option 3.** Pre-start (and paused-session) events are refused and never replayed; the thread is where that content lives | The owner's call. Replay (option 1) needs a bounded per-item record of what was refused; a durable "gave up" marker (option 2) needs the same state to render a status line. Option 3 needs none — its whole cost is honesty. |
| D2 | Option 3 is only *true* if the session is told to read the thread, so the **spawn prompt** now says so | The prompt already framed the thread as untrusted content; it never asked the session to read it. The claim "the content is not lost" was resting on nothing. One sentence, in the prompt's trusted voice, in both copies the parity test holds identical. |
| D3 | A delivery id gains a third fate: **settled** — the dispatcher is finished with it | It always had three (enqueued, released, kept-with-nothing-coming); only two had names, so the third was read as one of them. Naming it is the whole fix. |
| D4 | The outcome lives **in the dedup entry**, not in a second cache | One eviction, one `discard`, one `dedupCacheSize` govern both. A parallel store needs its own bound and can disagree with the deduper about which ids are known — the class of bug being fixed. |
| D5 | A settled comment is **baselined**, never written to `gaveUp` | `gaveUp` means "a failing environment beat us", and a later version re-arms it. Recording a refusal there is how replay-on-upgrade was built by accident. |
| D6 | `done` outranks `settled` | An event can be delivered into a work item's session while a second endpoint of the same record is paused. A suppression on one endpoint must not un-deliver the other. |
| D7 | The three **control** outcomes settle too — executed, rejected, ambiguous | A `the-loop stop` before any start is the ticket's own scenario reached through the control path, and often the *first* comment on a labelled item. Its ledger entry was stuck identically, and its restart tail is worse than a false notice: the poller re-forwards the comment and the-loop **executes the command again** — for `cleanup`, releasing local resources twice. Fixing one and not the other would have made the rule arbitrary. |
| D8 | `session-occupied`, `session-vanished`, `work-item-not-found` and every failure path are **untouched** | They keep their ids for different reasons. `session-occupied` is operator-fixable (kill the stale tmux session), and today's stuck entry is what lets a later redelivery succeed once they have — baselining it would remove a recovery path to fix a cosmetic one. |
| D9 | Resolve **synchronously**, on the cycle the refusal happens | Leaving it to the next cycle would still record one real attempt and emit one misleading `poll.comment_forwarded` per refused comment — a smaller copy of the reported bug. |
| D10 | One new event, `poll.comment_settled`, rather than reusing `poll.comment_forwarded` | The forward event means "handed over, attempt N". A settlement is the opposite of an attempt; overloading it would make `attempt` mean two things. |
| D11 | No config key, no schema change, and the settled mark stays **process-local** | There is no deployment that wants the ledger to lie. And a settlement is bookkeeping about a delivery, not a durable fact about the work item — the durable half already exists (the baselined comment id), written on the first cycle. |

## Consequences

**Good.** The ledger stops lying: a refused comment leaves nothing pending, spends no retry
budget, produces no false "we could not deliver this" notice on the ticket, and cannot be
re-armed into a late replay by an upgrade. The pre-start rule is now written where a reader
meets it — the capability doc, the state reference, the polling options — and where the
*agent* meets it, in the spawn prompt. A control comment stops being accounted for as a
delivery, which also closes most of the window in which a restart could execute a `cleanup`
twice. The poller does strictly less work per cycle than before.

**Costs, accepted.** One more string per live dedup entry, and one more state in a status
enum that three call sites read. The settled mark dies with the process (D11), so between a
refusal and the first poll cycle a restart still reverts to the old accounting — bounded by
one cycle, where it used to be unbounded. And the deliberate part remains deliberate: a
pre-start comment is still never delivered as an event. If that turns out to be wrong,
option 1 is a separate decision, and this one makes it cheaper by having named the state it
would need.

**Out of scope, deliberately.** A durable per-item record of what was refused (option 2's
status line), a `poll.cycle` counter for settlements, and the three drop reasons in D8.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Replay on start (option 1) | The owner declined it. It needs a bounded per-work-item record of every refused delivery — the unbounded version is the redelivery flood the current refusal exists to avoid. |
| A durable "gave up before the start" marker (option 2) | Same state cost as option 1 for a line in `the-loop status`, when the same fact is already visible as `dispatch.dropped` and now as `poll.comment_settled`. |
| Reuse `gaveUp` to record the refusal | It is the re-arm mechanism (D5). That is how the accidental replay exists in the first place. |
| A second cache keyed by delivery id | Two bounds, two evictions, and a way for the two to disagree (D4). |
| Have the poller infer a refusal from the `dispatch.dropped` event log | Turns the observability log into a control channel, and makes retry accounting depend on log retention being on. |
| Release the delivery id for `awaiting-start` instead | Exactly the flood issue-106 documented: GitHub redelivers and the poller re-forwards every comment on every labelled, unstarted item, every cycle, until each one's budget is spent. |
