---
type: bugfix
phase: requirements-definition
workItem: issue-159
status: approved
approvedBy: []
severity: high
collaborators: [engineer]
overrides: {}
---

# Bugfix spec: the poller is not idempotent across a stop/restart

> Phase 1 of 3 for a bug (bugfix → design → tasks). Human approval for this
> tier-3 change happens at the PR (`autonomy.tiers."3": human-approves-pr`).

## Summary

As reported on [issue #159](https://github.com/MadaraUchiha-314/the-loop/issues/159):
the poller has to be stopped and restarted for operational reasons (a config
change the hot reload does not cover, an upgrade, a host reboot, a systemd
restart, a cron-driven `--once`), and **starting and stopping should have no
effect** — a restarted poller must behave exactly as one that never stopped.

Most of that already holds, and by design: the per-work-item ledger
(`portable/<slug>.json`, issue-128) is durable, comment delivery ids are
deterministic, and `recentDeliveries` on the session record survives a restart
(issue-80/94/146). What does *not* hold is everything around the ledger — the
process lifecycle. Five defects, each of which makes a restart observable:

**B1 — two pollers can run against the same state.** `poll start` writes its
pidfile unconditionally and never checks whether a poller is already running.
`poll stop && poll start`, a supervisor that restarts before the old process has
exited, an operator with two terminals, or two overlapping `--once` runs from
cron all produce two pollers sharing one ledger. `PollState` reads an item's
record on first touch and writes it back at the end of the cycle, so two pollers
interleave read-modify-write over the same file: each re-forwards comments the
other had already baselined, and each can spend the other's retry budget. This
is the sharpest form of the reported problem — restarting *does* have an effect,
and the effect is duplicate delivery.

**B2 — the pidfile is trusted without verification, and `stop` does not wait.**
After a `SIGKILL`, a host crash or an OOM kill the pidfile survives with a pid
that is not the poller's. `poll stop` reads it and sends `SIGTERM` to whatever
process now owns that pid — on a busy host, pid reuse makes that somebody else's
process. And even in the happy path `stop` returns as soon as the signal is
*sent*, not when the poller has exited, so the `stop && start` an operator
actually types is a race against B1.

**B3 — a kill mid-cycle discards the whole cycle's ledger.** `PollState.save()`
runs once, after every provider and every item. Records are already one file per
work item, written atomically — there is no reason to batch them — yet a poller
killed while processing item 40 of 50 loses what it learned about items 1–39.
The next start re-baselines first-sight items (silently swallowing comments
posted in the meantime, which the spawned session would otherwise have been told
about), re-forwards comments whose delivery never resolved, and resets spawn
attempt counters. A hard kill cannot be made free, but its blast radius should
be the item in flight, not the cycle.

**B4 — a shutdown is not observed inside a cycle.** `Poller.run` checks
`stop_event` only between cycles. `poll_once` walks every provider and every
item regardless, and a single dispatch can block for up to
`routing.dispatchTimeoutSeconds` (default 1800). So `SIGTERM` can take many
minutes to take effect, and every work item processed in that window is a
session spawned or a comment forwarded *after* the operator asked the poller to
stop — the "stopping should have no effect" half of the report, from the other
side.

**B5 — a graceful stop spends retry budget it never used.** The poller records a
delivery attempt when it *enqueues* an event and observes the outcome on the
next cycle (issue-80). On shutdown, `Dispatcher.stop()` drains what it can
within its join timeout and the process then exits, abandoning whatever is left
in the queues. Those events were counted as attempts but never delivered, so
three unlucky restarts exhaust `polling.maxRetries` and the poller *permanently*
gives up on a comment that was never once dispatched — and `gaveUp` is
version-gated (issue-146), so nothing re-arms it until the CLI is upgraded.

## Steps to reproduce

**B1.** Start a poller (`the-loop poll start`). In a second terminal, start
another with the same config. Both discover the same labelled items; watch the
same comment forwarded twice (`poll.comment_forwarded` twice for one comment id
in `the-loop events --source poll`) as each poller writes a `poll` section the
other had not read.

**B2.** `kill -9` a running poller. `<state.root>/poll.pid` still holds its pid.
Run `the-loop poll stop`: it reports success and signals that pid. Alternatively
run `the-loop poll stop && the-loop poll start` against a healthy poller with a
long cycle in flight — `start` runs while the old process is still finishing, and
B1 follows.

**B3.** Configure two sources with many labelled items. `kill -9` the poller
mid-cycle. Compare `<state.root>/portable/*.json` before and after: nothing the
interrupted cycle learned was written.

**B4.** With `routing.dispatchTimeoutSeconds` at its default and a work item
whose tmux delivery hangs, send `SIGTERM`. The poller keeps spawning sessions
for the remaining items in the cycle before it stops.

**B5.** Send `SIGTERM` while several comment forwards are queued. Restart. The
ledger's `commentAttempts` counts them, but no session ever received them.
Repeat three times: `poll.comment_failed` with `will_retry=false`.

## Expected vs actual

- **Expected:** `poll stop` followed by `poll start` is indistinguishable, in
  everything the poller does afterwards, from a poller that was never stopped —
  no duplicate spawn, no re-forwarded comment, no swallowed comment, no retry
  budget consumed, and no window in which two pollers act on one ledger.
- **Actual:** the durable ledger makes the *common* restart clean, but the
  process lifecycle around it does not: overlap is unguarded, `stop` is
  unverified and non-blocking, a hard kill loses a whole cycle's writes, a
  shutdown is not observed inside a cycle, and a graceful stop burns retry
  budget on undelivered events.

## Root cause (confirmed by reading the code)

The durable state was designed for idempotency (`PollState`'s docstring says so)
but the *process* around it was not. Concretely:

| # | Where | What |
|---|---|---|
| B1 | `commands/poll.py::_start` | writes the pidfile, never takes an exclusive lock; `--once` writes nothing at all, so cron overlap is invisible |
| B2 | `commands/poll.py::_stop` | `os.kill(int(pidfile.read_text()), SIGTERM)` — no proof the pid is *this* poller, no wait for exit |
| B3 | `poller/poller.py::poll_once` | one `self.state.save()` after every provider, though `WorkItemStore.write_section` is already per item and atomic |
| B4 | `poller/poller.py::poll_once` / `_poll_provider` | no `stop_event` below the run loop |
| B5 | `webhook/dispatcher.py::stop` | drains best-effort and drops the remainder on the floor; the poller is never told which events died with it |

## Requirements

### Requirement 1 — at most one poller per state root

**User story:** as an operator restarting the poller, I want the second poller to
refuse to start rather than quietly share a ledger, so that a restart can never
double-deliver.

- 1.1 WHEN `poll start` is invoked AND another poll process is already running
  against the same state root, the system SHALL refuse to start, name the running
  poller's pid and pidfile, and exit non-zero without touching the ledger.
- 1.2 The exclusion SHALL apply to `--once` runs as well as to the run loop, so
  two overlapping cron invocations cannot interleave.
- 1.3 The exclusion SHALL be scoped to the state root: two pollers configured
  with different `state.root` values SHALL both be allowed to run.
- 1.4 WHEN the previous poller died without cleaning up, the system SHALL detect
  the leftover pidfile as stale and start normally — a crash SHALL NOT require
  manual cleanup before the poller can run again.
- 1.5 The mechanism SHALL be released by the operating system when the process
  dies, by any means including `SIGKILL`, so no liveness heuristic can strand it.

### Requirement 2 — `stop` is verified, and blocks until the poller is gone

**User story:** as an operator scripting `stop && start`, I want `stop` to be
true when it returns, so that the restart cannot overlap the shutdown.

- 2.1 WHEN `poll stop` finds a pidfile whose process is not a running poller, the
  system SHALL NOT signal that pid; it SHALL report the pidfile as stale, remove
  it, and exit non-zero.
- 2.2 WHEN `poll stop` signals a running poller, it SHALL wait until that poller
  has actually exited before returning success, bounded by a timeout.
- 2.3 IF the poller has not exited within the timeout, `poll stop` SHALL say so
  and exit non-zero rather than report a success that has not happened.

### Requirement 3 — a hard kill loses at most the item in flight

**User story:** as an operator whose host was rebooted mid-cycle, I want the
poller to resume where it was, so that a cycle interrupted by force does not
replay or swallow work for items it had already finished.

- 3.1 WHEN the poller finishes processing a work item, it SHALL persist that
  item's ledger before moving to the next one.
- 3.2 WHEN processing a work item raises, the poller SHALL still persist what
  that item's ledger already recorded (an attempt already spent must not be
  re-spendable), and continue with the next item as it does today.
- 3.3 A cycle SHALL remain a single logical pass: per-item persistence SHALL NOT
  change which items are processed, in what order, or what is dispatched.

### Requirement 4 — a shutdown is honoured inside a cycle

**User story:** as an operator stopping the poller, I want it to stop within one
work item rather than one cycle, so that "stopped" means stopped.

- 4.1 WHEN a stop is requested during a poll cycle, the poller SHALL finish the
  work item in flight, persist it, and process no further items or providers.
- 4.2 WHEN a cycle is cut short for any reason, the poller SHALL NOT run closure
  reconciliation for the affected source: a partial listing is not evidence that
  the unlisted items ended, and treating it as such would close live sessions —
  the same rule issue-94 already applies to a *failed* listing.
- 4.3 The interrupted cycle SHALL be reported as interrupted in the cycle summary
  and in the event log, so a short cycle is legible rather than mysterious.

### Requirement 5 — a graceful stop returns unused retry budget

**User story:** as an operator who restarts the poller regularly, I want restarts
not to accumulate toward the give-up threshold, so that a comment is only ever
abandoned because delivery genuinely failed.

- 5.1 WHEN the dispatcher is stopped with events still queued, it SHALL report
  which deliveries it abandoned rather than dropping them silently.
- 5.2 WHEN the poller shuts down with abandoned deliveries, it SHALL release the
  attempt it recorded for each of them and persist the correction, so the next
  start retries them with the budget it started with.
- 5.3 An abandoned delivery SHALL NOT be baselined: releasing an attempt SHALL
  leave the event unresolved, exactly as if it had never been enqueued.

## Security considerations

**Threat model.** The change touches process lifecycle and on-disk state under
`state.root`; it adds no network surface, no new external input, and no new
payload-derived value reaches an argv, a path or a prompt.

- **Signalling a process that is not ours (fixed, not introduced).** Today
  `poll stop` will `SIGTERM` any pid a stale pidfile happens to name. Requirement
  2.1 removes that: the pid is signalled only when the lock proves a poller holds
  it. This is a security *improvement* — an attacker who can write the pidfile
  (i.e. already has write access to `state.root`) can currently make `the-loop`
  kill an arbitrary process the operator owns.
- **The lock file is in the trust boundary already.** It lives under
  `state.root`, alongside the ledger and the session registry; anyone who can
  write it can already write the records the poller acts on. It carries no
  secret — a pid, which the pidfile publishes anyway — and is never read as
  instructions.
- **Denial of service by lock squatting.** A local process holding the lock
  prevents the poller from starting. That is the intended behaviour (R1.1) and
  is bounded to principals who can already write `state.root`; the refusal names
  the holding pid so the operator can see what is holding it.
- **No change to authorization.** `authorizedUsers`, the self-reply marker and
  the control-command guards are untouched. Releasing a retry attempt (R5.2)
  operates on delivery ids the poller itself minted; it cannot resolve, un-resolve
  or re-authorize a comment.
- **Fail-safe direction.** Every new failure path fails *closed for action*:
  cannot take the lock ⇒ do not poll; cannot prove the pid is a poller ⇒ do not
  signal; cycle cut short ⇒ do not reconcile closures.

## Out of scope

- The `gh-webhook` receiver's pidfile handling, which has the same B1/B2 shape.
  It is a separate ingress with a separate ticket-worthy blast radius; the lock
  helper introduced here is written to be reusable by it, but wiring it in is not
  part of this change.
- Making a `SIGKILL` free. R3 bounds the loss to one work item; it does not
  eliminate it, and cannot — the process can die between the dispatch and the
  write no matter how the write is scheduled.
- Any change to `polling.maxRetries` semantics, the give-up/re-arm gate
  (issue-146), or the closure-reconciliation rules (issue-94) beyond R4.2.
