---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#453"
---

<!-- Authored per the the-loop:writing skill. -->

# Self-review: a parked work item is owned by the instance that accepted it

> The self review before human review
> ([`reference/reviewing.md`](../../../../skills/the-loop/reference/reviewing.md)). I read
> the branch diff adversarially, asking what else the new source of ownership lets
> through, what a closure could still leave armed, and what a reviewer would reject.

## Review cycles

### Cycle 1: what the new source grants

1. **Checked: one guard, four verbs.** `_authority` serves `pr create`, `pr merge`,
   `pr resolve-thread` and `ticket close`. The new clause reads the record for the
   **target** only, so a parked `--work-item` still cannot merge a stranger pull request
   (tested). A pull request that is itself the parked work item may be acted on, which
   is the same rule a session-backed PR work item already has.
2. **Found and fixed: the command was going to be inspected.** A first draft accepted
   only arming commands. That broke idempotency: the first close records `stop`, and
   the second would have been refused. The guard now takes any record this instance
   wrote while the item is not `ended`, which is also how `_managed_here` and
   `describe_instance` already count the managed set (issue-322). Said so in
   decision-141 D3 and in the capability doc.
3. **Checked: the instance name comes from the config.** `core_sessions._instance`
   reads it through `instance_config`, the one construction (decision-109 D1). The
   record's own field is compared, never trusted back. Named-on-unnamed and
   unnamed-on-named are both refused (tested).

### Cycle 2: the closure

1. **Checked: the stop is the real one.** `ControlStore.record(target, STOP, source=
   "cli", instance=…)` is byte-for-byte what `sessions stop` writes, so the spawn gate
   (`start_requested`) reads it identically; the integration test drives a labelled
   event **and** a synthesised `control-start` through the real dispatcher afterwards
   and sees no spawn.
2. **Checked: a GitHub refusal leaves the item armed.** The cancellation runs only after
   `close_issue` returned; on an error the function returns before it (tested).
3. **Found and fixed: a write failure after the close was silent.** The ticket is closed
   on GitHub whether or not the local record can be written; the first draft swallowed
   the exception. It now exits 0 with `startCancelled: false` and a stderr line naming
   `sessions stop` as the remedy. Not unit-tested as a distinct case: the path is three
   lines and the message is the only behaviour.
4. **Checked: the session-backed path is untouched.** With a live session the function
   returns before reading the store; the record keeps its `start` and the daemon's
   `closed` event still ends the item (tested end to end).

### Cycle 3: no new findings

Re-read the diff after the fixes; the eventlog record reuses `control.command` with
`effect: start-cancelled` rather than inventing a type. Stopping per the procedure.

## Critic reviews

Not run in this session: no critic harness is installed in this cloud checkout (`the-loop
critic list` is unavailable; the CLI is not installed as a service here). The PR's own
review bot and the human reviewer are the remaining rounds.
