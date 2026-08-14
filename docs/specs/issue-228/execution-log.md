---
type: execution-log
workItem: issue-228
phase: implementation
status: in-progress
---

# Execution Log: one `the-loop start` for every service the config enables

> Append-only log for issue-228. Ticket:
> [#228](https://github.com/MadaraUchiha-314/the-loop/issues/228).

## How this session ran the loop

One cloud session, one pass — the posture of issue-208 through issue-224, with the same
two consequences a reviewer should hold:

1. **`phase-selection` was not run as a gate.** The session was started from the ticket;
   there was nobody to tick the checklist. Phases assumed: full spec chain,
   implementation, verification, self-review. `brainstorming` not taken (the ticket
   enumerates the wanted commands itself); the opt-in `design-critic-review` not taken
   (no second model available to this session).
2. **The chain was authored before the code, but approved by nobody.** All four
   artifacts are `status: draft` — a proposal to ratify with the PR. Risk tier **3**
   (see `requirements.md` §Risk tier) ⇒ human approves the PR; no separate named
   security sign-off.

Mid-session the operator asked (chat) for a rebase onto the freshly merged `main`
(issue-225, v9.15.0) before implementation; done — recorded here as the paper trail for
that instruction.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-14 | — | Not run as a gate; see above |
| requirements-definition | 2026-08-14 | | [`requirements.md`](requirements.md) — 5 requirements, 5 NFRs, security §, risk tier 3 |
| design | 2026-08-14 | | [`design.md`](design.md) — 5 design points, decision-084 |
| test-planning | 2026-08-14 | | [`testing-plan.md`](testing-plan.md) — 12 activities, 5 n/a rows with reasons |
| tasks-breakdown | 2026-08-14 | | [`tasks.md`](tasks.md) — 12 tasks |
| implementation | 2026-08-14 | | 12 tasks; ~60 files (4 new modules, 1 deleted command, both schema copies, 30+ documents) |
| verification | 2026-08-14 | | Testing plan executed; see [`evidence/verification.md`](evidence/verification.md) |
| needs-review | 2026-08-14 | | Handed to the PR |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| `claude/github-issue-228-weq41j` | the whole work item | open, awaiting human approval |

## Progress entries

### 2026-08-14 — orientation

Read the ticket, CLAUDE.md, the skill, the harness config, and the whole current
lifecycle surface: `commands/poll.py` (629 lines — parser, run loop, daemonize, status,
stop), `commands/gh_webhook.py`, `commands/service_cmd.py`, `api/serve.py` +
`api/app.py` + `api/mcp.py`, `core/daemons.py`, `daemon_entry.py`, `client` auto-start,
both CLI-config schema copies. Three findings shaped the design:

- **No `enabled` exists anywhere in the CLI config** — the flags the ticket assumes have
  to be added, and their defaults argued (design D1).
- **The poller's only implementation lives inside the command being removed** —
  `daemon_entry` literally re-parses `poll start`'s parser. Extraction before deletion.
- **A service cannot synchronously restart itself over its own API** — hence the
  scheduled-restart contract (design D5).

### 2026-08-14 — building it

Order: the four `enabled` flags (schema copies + template + `service_config`), the MCP
mount flag, then the poller extraction, then the composition layer, then the API route,
then tests and documents. Four things came out of doing it rather than planning it:

1. **The decision number collided.** The rebase the operator asked for brought in
   issue-225, which had already minted decision-083; this work item's record was
   renumbered to **decision-084** and issue-225's file restored untouched. The kind of
   conflict two same-day cloud sessions produce — caught because the Write reported an
   *update* where a *create* was expected.
2. **The receiver's pidfile was not a lock.** `gh-webhook start` wrote a plain pid file,
   while `core.daemons.daemon_status` — and now `the-loop start`'s honest-start wait —
   answer liveness from the pidfile's flock. A foreground receiver therefore read as
   *not running* on the daemons API before this change. The receiver now takes a
   `RunLock` exactly as the poller does (and its `stop` became verified and blocking),
   which is in scope because `start` cannot prove a receiver came up without it.
3. **`daemonize()` died with its only caller.** The issue-191 double-fork existed for
   `poll start --daemon`; every remaining detached start is
   `Popen(start_new_session=True)` with the logfile on fds 1/2, and `start` proves
   liveness by waiting for the lock instead of the pipe handshake. `open_logfile`
   survives (both spawn paths use it).
4. **The heartbeat detail had to travel.** `poll status`'s JSON carried the last cycle's
   counters; `daemon_status` does not. `status_all` reads the heartbeat into the poller
   row (`lastCycle`, `intervalSeconds`) so removing the command lost no fact (R2.4).

### 2026-08-14 — re-pointing the tests

The poll-command suites were **re-pointed, not deleted** (testing-plan §2): every
scenario keeps its Gherkin and asserts through the new entry points —
`daemon_entry poller [--once]` for the run-loop properties (ttyd parity, the
single-instance lock, crash recovery), `the-loop start` for the detach properties
(own session, outliving the starter's process group, honest failure reporting, stale
pidfile cleanup), `the-loop status` for the liveness-is-the-lock invariants (forged
heartbeat, stale pidfile, heartbeat-as-enrichment). The fork-specific scenarios
(zombie reaping, `--daemon --once` contradiction) died with the mechanism. Two new
files (`test_core_lifecycle.py`, `test_lifecycle_cmd.py`) cover composition; the
restart route and the MCP flag landed in the existing integration suites; the OpenAPI
contract gained `/api/v1/restart` (parity-tested).

### 2026-08-14 — self-review

Three rounds over the full diff, findings fixed in place:

1. **Round 1 — the collision and the tables.** The decision-083 clobbering (above), and
   markdownlint catching unescaped `|` inside code spans in the three new capability
   history rows.
2. **Round 2 — what a save must report.** `service.mcp` is boot-time (the mount happens
   in `create_app`), so it was added to `core.config.RESTART_REQUIRED` — without it the
   issue-222 editor would claim a saved MCP toggle was live.
3. **Round 3 — the stragglers.** A final `the-loop poll` sweep caught four code
   docstrings still naming the removed command; `_print_rows` on an empty list; the
   test race where `stop` returns at lock-release, a moment before the process
   finishes dying.

No round produced a repeated finding, so nothing escalated.

## Capability docs

- [`docs/capabilities/cli.md`](../../capabilities/cli.md) — the lifecycle-surface
  behaviour rewritten around `start|stop|status|restart` (the old `poll start --daemon`
  / `poll status` clauses replaced by the honest-start and unified-status rules);
  history row added.
- [`docs/capabilities/control-plane.md`](../../capabilities/control-plane.md) — the
  restart endpoint, its MCP exclusion, the disableable `/mcp`, and the local-by-nature
  command list updated; history row added.
- [`docs/capabilities/webhook-triggers.md`](../../capabilities/webhook-triggers.md) —
  the poller-lifecycle clauses re-pointed at the new surface (the double-fork clause
  replaced by the lock-wait rule); history row added.
- [`docs/capabilities/interactive-sessions.md`](../../capabilities/interactive-sessions.md)
  — two ingress-naming clauses reworded; no behaviour change.

## Documentation

- `docs/cli/commands/` — `poll.md` deleted; `start.md`, `stop.md`, `status.md`,
  `restart.md` added; `index.md`, `gh-webhook.md`, `migrate-config.md` re-pointed;
  sidebar (`docs/.vitepress/config.mts`) updated.
- `docs/config/cli/` — `enabled` documented on the polling/webhook pages,
  `enabled` + `mcp.enabled` on the service page; `index.md`, `routing-options.md`
  re-pointed.
- `docs/cli/getting-started.md`, `installation.md`, `state.md`, `index.md` — quickstart
  and state pages follow the new surface (`daemon_entry poller [--once]` as the
  cron/systemd form).
- `docs/api-specs/openapi/the-loop.v1.yaml` — `/api/v1/restart` + `RestartBody`.
- `README.md` and `cli/README.md` — the front-page command examples.
- `skills/the-loop/templates/cli-config.yaml` — the four new keys, commented.
- `skills/the-loop/reference/observability.md` — process naming only.
- `docs/decisions/decision-084.md` + index row.
- `skills/the-loop/SKILL.md` and `reference/automation.md` needed no change: neither
  names the poll commands.
