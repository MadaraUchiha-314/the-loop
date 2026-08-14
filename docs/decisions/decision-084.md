# Decision 084: one lifecycle surface (`start|stop|status|restart`) driven by per-service `enabled` flags

- **Status:** proposed
- **Date:** 2026-08-14
- **Work item:** [issue-228](https://github.com/MadaraUchiha-314/the-loop/issues/228)
- **Deciders:** maintainer (via ticket); harness (proposal)

## Context

the-loop grew from a poller into four services — poller, webhook receiver, REST
control-plane service, MCP layer — but the way an operator brings it up stayed
poller-shaped: `the-loop poll start`, with the receiver and service on sibling commands
and the service also auto-started implicitly by any CLI invocation. The ticket asks for a
dedicated `the-loop start` that reads the CLI config and starts what is enabled, removal
of the poll commands, and `the-loop restart [--with-upgrade]` as both a command and an
API.

## Decision

1. **Four additive booleans decide composition:** `service.enabled` (default true),
   `service.mcp.enabled` (default true), `webhooks.ghWebhook.enabled` (default false),
   `polling.enabled` (default false). Network-listening ingresses are explicit opt-ins;
   the service and MCP keep their long-standing on-by-default behaviour. Enablement is
   never inferred from a block's presence or a non-empty `sources` list (the
   one-question-two-answers trap).
2. **`the-loop start|stop|status|restart` compose existing runtimes** through a new
   `core.lifecycle` facade; they are bootstrap commands (the decision-058 exception,
   like `service`). `stop` ignores `enabled` (a disabled-after-start service must still
   stop); `status`'s exit code means "everything enabled is running".
3. **The `poll` command is removed; its run loop moves** to `poller/daemon.py`, driven
   by `daemon_entry poller [--once]`. The issue-191 double-fork (`daemonize()`) goes
   with it — every remaining detached start is one idiom,
   `Popen(start_new_session=True)` with a logfile; `start` proves liveness by waiting
   for the daemon's pidfile lock instead of the ready-handshake.
4. **`POST /api/v1/restart` schedules** a detached, fixed-argv
   `python -m the_loop restart [--with-upgrade]` and answers immediately — a service
   cannot stop itself synchronously and still respond. It is deliberately **not** an MCP
   tool: it tears down the MCP transport mid-call, and `--with-upgrade` reaches the
   installer an agent must not drive.
5. **`--with-upgrade` reuses the issue-152 planner**, CLI component only; an upgrade
   failure is reported but never leaves the system down (the start half still runs).
6. **Fail closed on disablement:** `service.enabled: false` also refuses implicit
   auto-start (`client.ensure_service`), while the explicit `the-loop service start`
   still works. `gh-webhook` and `service` commands are kept (the ticket removes poll
   commands only).

## Consequences

- Breaking CLI change (`poll` gone) — declared in the commit; cron/systemd users of
  `poll start --once` move to `python -m the_loop.daemon_entry poller --once`.
- No config migration: keys are added, none removed or moved.
- The dashboard gains a restart affordance for free (REST route); wiring it into the UI
  is future work.

Spec: [docs/specs/issue-228/](../specs/issue-228/requirements.md)
