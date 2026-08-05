---
type: execution-log
workItem: "issue-159"
phase: needs-review
status: in-progress
---

# Execution Log: the poller's process lifecycle becomes as idempotent as its ledger

> Append-only log of progress for the user's visibility. Checked in alongside
> the spec at `docs/specs/issue-159/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-05 |  | Issue #159: the poller must be stoppable and restartable with no effect. The per-item ledger was already restart-safe; five lifecycle defects were not. |
| design | 2026-08-05 |  | Three mechanisms: an exclusive lock held on the pidfile itself, per-item persistence + cooperative shutdown, and returning the retry budget of abandoned dispatches. No new config, no new generated path. |
| tasks-breakdown | 2026-08-05 |  | 12-task DAG; the lock primitive first, the poll loop and the dispatcher independently, then docs. |
| implementation | 2026-08-05 |  | On `claude/github-issue-159-79e8xf`. |
| needs-review | 2026-08-05 |  | PR opened; tier-3 human approval happens there. |
| complete |  |  |  |

## Pull requests

| PR | Branch | Status |
|----|--------|--------|
| _(pending)_ | `claude/github-issue-159-79e8xf` | open — awaiting tier-3 human approval |

## Progress entries

### 2026-08-05 — spec drafted

- **Phase:** requirements → design → tasks
- **Did:** read the whole poll path (`Poller.poll_once`/`_poll_provider`/
  `_process_item`/`_try_spawn`/`_process_comment`, `PollState`,
  `WorkItemStore`, `Dispatcher.handle`/`delivery_status`/`stop`, `commands/poll.py`)
  looking specifically for what a stop/start changes. Confirmed the ledger side
  is already sound — deterministic comment delivery ids, durable
  `recentDeliveries`, atomic per-item records (issue-80/94/128/146) — and that
  the gaps are all in the process lifecycle.
- **Found (five):** (B1) nothing prevents two pollers sharing one ledger, so a
  restart that overlaps double-delivers; (B2) a stale pidfile is signalled
  blindly and `stop` does not wait, so `stop && start` races; (B3) the ledger is
  flushed once per cycle, so a kill loses every item the cycle had finished;
  (B4) a shutdown is not observed inside a cycle, so `SIGTERM` keeps spawning
  for minutes; (B5) a graceful stop spends retry budget on events it never
  delivered, and three restarts can permanently abandon a comment.
- **Decided:** the lock **is** the pidfile — one file, so "who is running" and
  "how do I signal them" cannot disagree — with `flock` rather than a
  pid-liveness probe (kernel-released on any death, per-inode scoping, race-free
  answer under pid reuse). Rejected a separate lock file (a second `GENERATED_PATHS`
  entry and a `.gitignore` line to avoid reusing a file that already means "the
  poller is here"), a durable dedup cache, and counting an attempt only once its
  failure is observed (re-opens the unbounded-retry hole issue-80 closed).
- **Next:** implement T1–T12 (TDD per task).

### 2026-08-05 — implemented, tested, documented

- **Phase:** implementation → needs-review
- **Did:** T1–T12. New `the_loop/runlock.py` (`RunLock`: acquire/release/holder/
  is_held/wait_until_free, `flock` with a documented pid-liveness fallback);
  `poll start` takes the lock before building anything and holds it for `--once`
  too; `poll stop` verifies the pid against the lock, refuses to signal a stale
  one, and waits for the release under a new `--timeout`; `PollState.flush(ref)`
  with `_poll_provider` flushing in a `finally` per item; `poll_once(stop_event)`
  checking between items and between providers, with `PollSummary.interrupted`
  and reconciliation skipped on a truncated listing; `Dispatcher.stop()`
  returning the delivery ids it abandoned; `PollState.release_comment_attempt` /
  `release_spawn_attempt` + `Poller.release_abandoned` wired into the shutdown.
  Three new event types (`poller.blocked`, `dispatch.abandoned`,
  `poll.attempts_released`).
- **Self-review findings, fixed:** (1) the naive open-then-flock had a
  stale-inode window — a holder unlinks before it closes, so a process that
  opened in between could lock an orphaned inode and believe it held the lock;
  `_open_locked` now compares the locked fd's inode with the one the path names
  and retries, pinned by a test. (2) a probe whose file vanishes between the
  existence check and the open reported "held", which would make `stop` signal a
  pid that had already gone; a missing file now propagates as `OSError` and
  reads as "not held". (3) `_attempted` was not cleared on the give-up paths, so
  the map's lifetime did not match its meaning. (4) `release_abandoned` now
  tolerates `None` from a dispatcher double.
- **Tests:** 40 new assertions across `test_runlock.py` (new),
  `test_poller.py`, `test_poll_command.py`, `test_routing.py` and
  `test_poller_integration.py` (Gherkin scenarios linked to the ACs). The
  load-bearing one is _an interrupted cycle never reconciles closures_: getting
  that wrong would close every live session below the interruption. `FakeTmux`
  gained a `deliver_gate` so a test can wedge a worker and leave an event queued
  without a sleeping thread.
- **Docs:** `docs/cli/commands/poll.md` (single-instance rule, `stop --timeout`,
  a "Stopping and restarting" contract, and the stale `--state-file` in the
  synopsis corrected to `--state-dir`), `docs/capabilities/webhook-triggers.md`
  (behaviour + history row), `docs/cli/state.md` (what `poll.pid` now means).
- **Evidence:** `make check` green — ruff, markdownlint (389 files), ruff format,
  pyright (0 errors), config validation, and 1262 tests passing (2 skipped),
  re-run three times for flakiness.
- **Next:** human approval on the PR (tier 3, `human-approves-pr`).
