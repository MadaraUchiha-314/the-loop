# Decision 132: a poll clock is a machine reading, not a fact about the work — both clocks leave the tracked record

- **Status:** proposed
- **Date:** 2026-09-18
- **Work item:** [issue-382](https://github.com/MadaraUchiha-314/the-loop/issues/382)
- **Deciders:** the-loop (design); MadaraUchiha-314 (owner, at the PR)
- **Refines:** [decision-046](decision-046.md) (generated state is split by whether it
  travels), [decision-115](decision-115.md) (the ledger-only closure schedule is measured
  on the ledger's own clock)

## Context

decision-046 split generated state by one question — *does this mean anything on another
machine?* — and put the work-item records in the tracked half because what an authorized
user armed, and which comments the poller has already seen, are facts about the world. The
`poll` section went with them, clocks included.

`lastPolledAt` is stamped on every cycle for every item the poller lists, and
`closureCheckedAt` once per window for every unlisted one. Both land in
`portable/<slug>.json`, which is tracked in git — so an operator whose `state.root` lives
in a repository (the-loop's own does) has a permanently dirty working tree and a diff
nobody wrote before every commit. [Issue-382](https://github.com/MadaraUchiha-314/the-loop/issues/382)
asks whether the value should be tracked at all.

It should not, and the reason is decision-046's own test rather than the annoyance: the
poller's other clock file, `poll-status.json`, is already local — "clock readings from one
machine's poller. Carried elsewhere they describe a process that is not there." A per-item
clock is that sentence per item.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **A poll clock is machine-local.** `lastPolledAt` and `closureCheckedAt` move to `<state.root>/local/poll-clocks.json`, keyed by ref — a work item's and a pull request's alike. | It is when a cycle on *this* box ran, not a fact about the work. It is also the only part of the `poll` section whose loss costs a **question** rather than a redelivery: without `seenComments` a whole thread is forwarded again; without a clock the item is merely due for its next closure check — one provider call, capped per cycle by decision-115. |
| D2 | **Both clocks move, not only the one the ticket names.** | `absent_since` compares them in one expression. Splitting them across a tracked and a local file would make one schedule read two stores and leave half the churn behind, for two values of the same kind. |
| D3 | **The split is at the storage boundary, not in the ledger.** The in-memory ledger keeps both keys; `_store_ledger` peels them off and `_load` merges them back. | Every caller — `finalize`, `baseline_comments`, `absent_since`, `note_closure_check`, the closure schedule — stays as it was, which is what keeps a storage change from becoming a behaviour change. One pair of methods is also the whole of the review surface. |
| D4 | **The upgrade is a read-fallback, not a migration.** A record that still carries a clock is read where the local file has none, and is written back without it on the first write that touches that ledger. | It runs once per record and dies with the last stale one. `the_loop.migrations` exists for config keys that changed meaning, not for a value the next cycle re-derives anyway. A migration command would be a step an operator can forget, for a value that costs one question if it is missing. |
| D5 | **The record is written only when its body changed.** | Once the clocks are out, "the record changed" and "the poller learned something" are the same statement — so a quiet cycle over *n* items writes one small local file instead of *n* records and *n* index rewrites. Leaving the write in would make the git-clean property depend on the bytes happening to match. |
| D6 | **The control plane still serves the clocks inside `poll`.** The core read surface joins this machine's clocks onto the record it returns. | The value is true on the machine serving it, and the dashboard's *last activity* has no other fallback for an item with no session. The split is about where state is stored, not about what a local reader may see — and the served shape being unchanged is why no UI, API schema or attention rule changed with it. |
| D7 | **No config key.** The file sits under `state.root` like every other generated file. | `state.root` is the one knob, and a second path to configure is a second thing to get wrong. |

## Consequences

**Good.** A repository holding `state.root` stays clean while the poller runs — the thing
the ticket asked for — and the tracked records now change only when the-loop learned
something, which makes their diffs readable as a log of the work. Two machines sharing
portable records no longer conflict on a timestamp neither can use. A forged clock also
stops being proposable through a pull request: the schedule reads a file that only the
operator's machine holds, which retires an attack surface issue-332's review had to argue
about.

**Costs, accepted.** A machine that receives portable records has no clocks for them, so
each ledger-only record is asked about once — capped at twenty per source per cycle — and
then dated. The `poll` section can no longer be read on its own as "when did we last see
this"; that answer is one file over. A crash between the clock write and the record write
leaves the clock ahead, which costs at most a deferred closure question (the ledger is
already idempotent about re-reading comment ids).

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Move only `lastPolledAt`, as the ticket names | leaves `closureCheckedAt` writing to the tracked record on the same schedule question; one comparison would read two stores |
| Keep both in the record and rely on identical bytes leaving git clean | the record would still be rewritten *n* times a minute, git is not the only reader of an mtime, and the property would hold by accident rather than by construction |
| One clock file per work item under `local/` | one inode per watched thread, for two short strings written by one process holding the single-instance lock |
| Put the clocks in the machine's per-work-item record (`local/<slug>.json`) | that file is the session registry's, and exists only where there is a session; a clock exists for every item the poller ever listed |
| A migration command or a version gate for the stale keys | a step an operator can forget, for a value the next cycle re-derives |
| Drop the clocks from the served record and change the dashboard | the value is true where it is served, and *last activity* would lose its only fallback for an item with no session |
