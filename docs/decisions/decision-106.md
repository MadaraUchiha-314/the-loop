# Decision 106: a poll source lists in scopes, a scope fails alone, and a permanent condition is surfaced once and re-probed slowly

- **Status:** proposed
- **Date:** 2026-09-02
- **Work item:** [issue-315](https://github.com/MadaraUchiha-314/the-loop/issues/315)
- **Deciders:** MadaraUchiha-314 (owner, via the ticket), the-loop (design)
- **Refines:** [decision-072](decision-072.md) (the heartbeat is enrichment beside the
  lock), issue-159 (a partial listing is not proof anything ended)

## Context

A GitHub poll source with thirteen repositories stopped delivering everything the moment
one of them had Issues disabled: the provider listed all repositories in one pass, the
first `gh` failure aborted the pass, the core recorded one `poll.provider_error` and
processed nothing, and `the-loop status` showed a running poller with `1 error(s)`. The
condition was permanent and was retried every minute for hours. The owner asked for
per-repository fault isolation, for "Issues disabled" to be classified as configuration
drift and not hot-retried, and for `status` to make the degradation visible.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The provider contract lists in scopes.** `PollProvider.listing()` returns a `Listing` — items plus the scopes that failed, were skipped or recovered — and the core consumes that. The default `listing()` wraps `list_work_items()`, so a provider that has not learned scopes fails as a whole exactly as before. | Isolation the core cannot see is isolation it cannot count, cannot show, and cannot keep out of closure reconciliation. A scope is the provider's word (a repository for GitHub, a project for Jira later); the core never learns what one is. |
| D2 | **A scope's failure costs that scope: no items from it, no closures in it.** Closure reconciliation skips every session whose `scope_of(ref)` is degraded. | Issue-159's rule — a partial listing proves nothing ended — is kept, at the grain that now exists. Under doubt the poller refuses to close; it never closes on a guess. |
| D3 | **Exactly one condition is permanent: `gh`'s "has disabled issues".** It quarantines the repository's *issues* only, for 60 cycles, surfaced once at warning level; pull requests are still listed; a re-probe that succeeds emits a recovery event, one that fails renews the skip silently. Everything else stays transient and isolated. | Only the reproduced condition is classified; a 404 is also what an expired token looks like. The quarantine lives in the provider instance, so a hot reload and a restart re-probe — the two moments the ticket's workaround showed recovery is wanted. |
| D4 | **The heartbeat carries the scope facts; `status` renders `degraded:` lines; the exit code does not change.** | The exit code is the documented keepalive primitive ("every enabled service is running"), and a degraded poller is running; restarting it would degrade identically. What was missing was words, not a signal. |

## Consequences

**Good.** One repository's failure is one repository's; the other twelve keep spawning
and forwarding. A disabled-Issues repository costs one warning and one skipped call per
cycle instead of one error and one wasted call. `status` names what is not being polled.
The seam admits any future provider's scopes without a core change.

**Costs, accepted.** A total `gh` outage now yields one event per repository per cycle
instead of one per provider. A pull-request session in a repository whose issues are
skipped is not reconciled until the repository recovers. The heartbeat carries `gh`'s
error text, as the event log already did.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Log per-repository failures inside the provider, keep the item-list contract | The core could neither count nor show them, nor keep them out of reconciliation |
| An exception that carries the partial items | A return value hidden in an error; every caller must catch to get results |
| Drop the quarantined repository from the source | Loses its pull requests; recovers only on restart |
| A durable quarantine under `state.root` | A new generated path for a fact a reload should forget |
| Flip the `status` exit code on degradation | Breaks the keepalive contract to say something a line of text says better |
