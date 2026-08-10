---
type: execution-log
workItem: issue-191
phase: needs-review
status: in-progress
---

# Execution Log: `poll start` runs as a proper daemon

> Append-only log for [#191](https://github.com/MadaraUchiha-314/the-loop/issues/191).

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-10 | pending — PR gate | Risk tier 3: process lifecycle and a new generated state file; no schema, no remote effect |
| design | 2026-08-10 | pending — PR gate | Two new modules, one new action, three new state paths |
| test-planning | 2026-08-10 | pending — PR gate | 15-row matrix; the fork is exercised for real, never mocked |
| tasks-breakdown | 2026-08-10 | pending — PR gate | 10 tasks, each naming its matrix row |
| implementation | 2026-08-10 | — | All 10 tasks complete |
| verification | 2026-08-10 | — | Every applicable row executed; see `testing-plan.md` § Verification results |
| needs-review | 2026-08-10 | pending | Self-review done; human gate is the PR |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#192](https://github.com/MadaraUchiha-314/the-loop/pull/192) (this repository) | Tasks 1–10 — the whole work item | open |

## Progress entries

### 2026-08-10 — spec chain locked

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** Read the ticket, then the operating model and the code the change lands in:
  `commands/poll.py`, `commands/gh_webhook.py`, `runlock.py`, `core/daemons.py`,
  `daemon_entry.py`, `poller/poller.py`, `state.py`, and the two tests that pin the
  contracts this touches (`test_state_portability.py`, `test_docs_parity.py`). Wrote and
  locked `requirements.md` → `design.md` → `testing-plan.md` → `tasks.md`.
- **Checkpoint/tests:** baseline `pytest -q cli` green — 1650 passed, 1 skipped.
- **Next:** implement tasks 1–10.
- **Blockers:** none.

### 2026-08-10 — implementation

- **Phase:** implementation
- **Did:** All ten tasks. New `the_loop.daemonize` (double-fork + `setsid`, stdio
  redirection, and a pipe handshake so the caller learns whether the daemon came up) and
  `the_loop.poller.heartbeat` (atomic per-cycle health file, warn-once on failure);
  `--daemon`/`--foreground`/`--logfile`/`--status-file` on `poll start` plus the new
  `poll status` action; three `StateLayout` paths with their `GENERATED_PATHS` entries;
  the poller's injected heartbeat callback; the control plane's start redirected to a
  logfile instead of `/dev/null`, `daemon_status` enriched, and `daemon_entry` pinned to
  foreground; and the documentation set.
- **Checkpoint/tests:** `make check` green — 1686 passed, 1 skipped, 0 lint/pyright findings.
- **Next:** self-review, then verification.
- **Blockers:** none.

### 2026-08-10 — self-review and verification

- **Phase:** verification → needs-review
- **Did:** Three self-review passes over the diff (findings under Review cycles). Executed
  every applicable row of the testing plan, plus a manual end-to-end walkthrough whose
  `ps` output is the ticket's claim in one line. Evidence committed under `evidence/`.
- **Checkpoint/tests:** `make check` green; the state-portability gate was observed
  failing first and then passing, which is what proves it guards anything.
- **Next:** human review on the PR.
- **Blockers:** none.

## Documentation

The user-facing docs that this change made wrong, corrected in the same PR:

| Doc | What changed |
|---|---|
| [`docs/cli/commands/poll.md`](../../cli/commands/poll.md) | The two new flags and the two new paths in the flag table; a **Foreground or daemon?** section (before/after the incantation, what `--daemon` does and why, log rotation as the host's job, supervision still out of scope); a `status` section with both renderings and the exit-code contract |
| [`docs/cli/state.md`](../../cli/state.md) | Three rows in the classification table, three sections (poller pidfile amended, heartbeat and poller log added), the layout tree, and the published `.gitignore` block |
| [`docs/cli/getting-started.md`](../../cli/getting-started.md) | The poll tab starts detached and checks `poll status`, with the foreground form kept for systemd |
| [`README.md`](../../../README.md), [`cli/README.md`](../../../cli/README.md) | The one-minute path starts the poller detached and watches it with `poll status` |
| [`docs/decisions/decision-072.md`](../../decisions/decision-072.md) + index | Why `--daemon` is opt-in rather than the default, and why nothing about it lives in the CLI config |

No config schema changed, so `docs/config/cli/polling-options.md` is untouched — this work
item deliberately adds **no** config keys ([decision-072](../../decisions/decision-072.md)).

## Capability docs

| Capability | What changed |
|---|---|
| [`cli.md`](../../capabilities/cli.md) | Four new behaviour rules: `poll start`'s foreground default and what `--daemon` guarantees; the pidfile written by the surviving process and stale ones removed; `poll status`'s contract, with liveness from the lock and never the heartbeat; and control-plane starts logging to a file. Plus the history row |
| [`webhook-triggers.md`](../../capabilities/webhook-triggers.md) | A sixth rule under *stopping and restarting the poller has no observable effect* — the process being tied to a terminal's process group was the last way it could vanish with no trace |
| [`control-plane.md`](../../capabilities/control-plane.md) | A daemon the core starts logs to a file, `daemon_status` carries it; and the "runs in the foreground" exception restated now that the daemons can detach themselves |

## Verification results

Recorded in [`testing-plan.md`](testing-plan.md) § Verification results — this work item
locked a testing plan, so the matrix rows and their outcomes live there.

## Review cycles

**Self-review, 3 rounds** (`reviews.selfReviewCount`), stopping on a round with no new
findings (`reviews.stopOnNoNewFindings`).

| Round | Found | Done about it |
|---|---|---|
| 1 | `poll status` rendered the liveness line through an unreadable expression; `daemonize` carried a logger it never used; a failed `fork()` would have surfaced as a traceback rather than a message | All three fixed: the liveness string is computed before the f-string, the logger is gone, and `OSError` from `daemonize` is caught and reported |
| 2 | Surfaces a new command action has to reach: `cli/README.md` still showed a bare `poll start`, `daemon_entry`'s module docstring still said the CLI's start is always foreground, and the MCP `daemon_status` docstring described the old three-key answer | All three updated |
| 3 | Nothing new. Checked the fd lifecycle across both forks (every write end closed on every path, so the handshake's EOF is reliable), the stale-pidfile unlink against `RunLock`'s stale-inode retry, and the heartbeat's behaviour under `--once` and under a restart | — (stop condition) |

**Critic review:** not run. `reviews.critics` is empty in this repository's
`harness-config.yaml`, so there is no configured second harness to run against; the human
gate on the PR is the review that applies.
