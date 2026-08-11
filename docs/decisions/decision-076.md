# Decision 076: The lock and the heartbeat are two files — and only the lock names the process

- **Status:** proposed
- **Date:** 2026-08-11
- **Deciders:** @MadaraUchiha-314 (owner), the-loop (engineer)
- **Work item:** [issue-205](https://github.com/MadaraUchiha-314/the-loop/issues/205)

## Context

A running poller leaves two files under `state.root`, and issue-205 asked the obvious
question: `poll-status.json` already had a `pid` field, so why is there a `poll.pid` too?

The two were introduced for different reasons and thirty-two issues apart.
`poll.pid` came from [decision-072](decision-072.md)'s ancestor work, issue-159: it is not a
file the poller writes *about* itself, it is the **flock** the single-instance guard is
held on, and the pid inside it is written under that lock so "who is running" and "how do I
signal them" cannot disagree. `poll-status.json` came from issue-191: the three facts a
lock cannot carry — `startedAt`, `lastCycleAt`, and what the last cycle did — so that
"is it making progress?" costs one command instead of a `ps`/pidfile/log cross-check.

The overlap was real but sat in one field. `pid` was written into the heartbeat on every
cycle and **read by nothing**: `poll status`, the control plane's `daemon_status` and every
client over it took the pid from `RunLock.holder()` from the day the heartbeat shipped.

## Decision

**Two files, one pid.** The heartbeat stops carrying a `pid`; `poll.pid` remains the only
place any surface learns which process is polling. The heartbeat keeps the progress facts,
and `Heartbeat.from_mapping` drops a `pid` left by an older poller like any other key it
does not model.

Merging the two files is rejected, on three grounds that pull in opposite directions:

1. **The lock lives on the inode; the heartbeat replaces the inode.** The heartbeat is
   rewritten `tempfile` + `os.replace` so a crash never leaves half a document — and
   `os.replace` puts a *new* inode at the path while the flock stays on the old one.
   Merged, the poller would free its own lock on its first cycle, and the next
   `poll start` would take it and run a second poller against the same ledger: exactly
   the defect issue-159 exists to prevent, on a 60-second timer. Writing in place instead
   trades that for a `poll status` that can read a torn document, and fixes neither of the
   points below.
2. **Opposite lifetimes.** The pidfile is unlinked on release, because a pidfile outliving
   its process is the stale-pid bug. The heartbeat is deliberately kept after the poller
   stops, so `poll status` can still report the last cycle *and* say the poller stopped
   after it.
3. **Opposite failure policies.** A pidfile that cannot be written aborts the start — a
   daemon that cannot prove exclusivity must not run. A heartbeat that cannot be written
   warns once and is swallowed — observability must never break ingress.

## Consequences

**Easier.** One question, one file: an operator reading `poll-status.json` by hand can no
longer find a pid there and signal it. The forgeable surface narrows — a hostile or stale
heartbeat can no longer even appear to name a live process — without changing any trust
boundary, since nothing read the field. And the reasoning above is now in the module
docstring, in `docs/cli/state.md` and here, instead of being re-derived from an issue
thread.

**Harder.** Nothing measurable. The heartbeat is machine-local generated state, never
committed and never read by another version of the CLI, so removing a key breaks no
contract; a heartbeat written before this change still reads. Anyone parsing the file with
`jq .pid` outside the-loop gets `null` — and was reading a field the tool itself ignored.

## Alternatives considered

- **Fold the heartbeat into `poll.pid`** — the issue's first branch. Rejected on the three
  grounds above; the first is disqualifying rather than merely awkward.
- **Fold the lock into `poll-status.json`** (lock the status file, keep one path).
  Rejected for the same reason viewed from the other side: the file that is atomically
  rewritten cannot be the file that is locked.
- **Keep the field and document it as advisory.** Rejected as the weakest form of the
  answer: a duplicate source of truth that a comment asks people not to trust is still a
  duplicate source of truth, and this issue is the evidence that it gets noticed and
  costs someone a reading.
- **Report the heartbeat's pid when no lock is held**, as a hint about the poller that
  stopped. Rejected: an unverifiable pid is at best noise and at worst something an
  operator signals — and `poll status` already reports the pidfile's recorded pid, under
  the lock's judgement, as `recordedPid`.
