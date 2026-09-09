# Decision 115: a ledger-only record is reconciled lazily — absent for a window on the ledger's own clock, asked once, capped per cycle

- **Status:** proposed
- **Date:** 2026-09-09
- **Work item:** [issue-332](https://github.com/MadaraUchiha-314/the-loop/issues/332)
- **Deciders:** the-loop (design); MadaraUchiha-314 (owner, at the PR)
- **Refines:** decision-113 D4 (closure reconciliation walks everything the machine tracks; poll-only records excluded)

## Context

decision-113 D4 excluded portable records carrying only `poll` from closure
reconciliation: the ledger of a thread once seen puts no urgent flag on the board, and
asking about it would cost one provider call per unlabelled open item per cycle, forever.
The consequence (issue-332) is that a closed item the poller once listed stays a plain row
on the control plane indefinitely — nothing ever stamps it — and the only remedy is a
full `the-loop reset`.

The ticket names four options and prefers lazy reconciliation: a poll-only record absent
from complete listings "for N consecutive successful cycles" gets one closure check, and
the stamp makes the set self-pruning. Three questions were open: how absence is measured,
how the cost is bounded, and whether any of it is configurable.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **Absence is measured in time, on the ledger, not as a cycle counter.** A record is due when the later of `poll.lastPolledAt` and the new `poll.closureCheckedAt` is at least `LEDGER_RECHECK_EVERY_CYCLES × intervalSeconds` old (sixty cycles — one hour at the default interval). | An in-memory counter never reaches N under `poll --once` from cron, where every cycle is a new process — and that is the shape the closed rows were reported from. A counter persisted per record would cost a record write and an index rewrite per absent record per cycle, the exact churn the per-item flush exists to avoid. The ledger already records the last cycle that saw the item; one more timestamp for the last cycle that asked about it makes "absent for a window" a comparison with no write. Expressed in cycles × interval so it reads in the ticket's vocabulary and follows a hot-reloaded interval. |
| D2 | **A non-closure is dated, and an unanswerable item is dated too.** *Still open* and `ProviderError` both write `closureCheckedAt`; only a closure stamps, through the unchanged close path. | One write per question, and the question recurs once per window per unlabelled open item — the bounded, mostly one-time cost the ticket asked for. Deferring the unanswerable case a window rather than retrying it next cycle is what keeps a record the provider cannot answer about (a planted number that does not exist) from sitting at the head of the queue and starving the rest under the cap. Nothing urgent waits on a ledger-only item, so a window's delay costs nothing. |
| D3 | **At most `LEDGER_CHECKS_PER_CYCLE` (twenty) questions per provider per cycle, longest-absent first.** | The first cycle after upgrade on a busy deployment could otherwise spend hundreds of `gh api` subprocesses in one cycle, with no stop-event check inside reconciliation. Twenty drains a hundred in five cycles; longest-absent first asks the likeliest-closed records, and each one asked is then stamped or dated, so the head of the queue always moves. |
| D4 | **No config key.** Window and cap are constants beside `_SEEN_COMMENTS_CAP`. | They are bounds on a background question, not policy; a key would be a schema change under `autonomy.sensitivePaths` for a knob with no stake to tune. issue-315 made the same choice for `REPROBE_EVERY_CYCLES`, the other slow re-probe. A deployment that needs a different window has a ticket to raise. |
| D5 | **The tracked set of decision-113 is unchanged** — no window, no cap, asked every cycle it is absent and unstamped. | Armed, frozen, rostered and session-backed items are the urgent set; issue-332 adds a second set with a schedule, it does not put the first on one. A record with `poll` beside another section belongs to the first set only. |

## Consequences

**Good.** A closed item the poller only ever listed leaves the plain rows by itself — its
record ends as `ended` only, demoted under *Shipped* or *Idle* as decision-113 renders it —
within a window of its closure plus at most a few cycles of cap. The cost is visible
(`ledger_checks` on the cycle's summary and `poll.cycle`), bounded per cycle, and once
per window per record that is open but unlabelled. `poll --once` from cron gets the same
behaviour as a long-running poller.

**Costs, accepted.** A closed ledger-only row stays up to an hour longer than a tracked
one (the window, at the default interval). An item whose label was removed but which stays
open is asked about once an hour for as long as its ledger exists — the recurring part of
the cost, one call per such item per hour. The `poll` section gains one optional field.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| An in-memory count of consecutive absent cycles | never reaches N under `poll --once`; resets on every restart |
| A per-record absent-cycles counter on the ledger | one write and one index rewrite per absent record per cycle |
| Reconcile ledger-only records with no window (the "opt-in provider calls" reading of the ticket's option 2) | the recurring per-cycle cost decision-113 excluded them for |
| A config key for the window / cap | a sensitive-path schema change for a bound with no stake; precedent is a constant (issue-315) |
| A board-side retention window (option 3) | hides open unlabelled items and leaves the fact unrecorded on disk; decision-113 deferred retention for *Shipped* on the same reasoning |
| A targeted CLI cleanup (option 4) | manual where the ticket asked for self-pruning; the stamped record `the-loop sessions reset` clears is already the end state |
| Retry an unanswerable ledger-only item next cycle, as the tracked set does | starves the cap under a planted or broken set; nothing urgent waits on a ledger-only item |
| Forget the `poll` section instead of dating it on a *still open* answer | loses the seen-comment baseline and the give-up record for an item that may be relabelled, and makes it first-sight again — a spawn candidate — for no closure |
