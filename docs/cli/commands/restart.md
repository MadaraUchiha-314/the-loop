# `restart`

Bounce the whole system — optionally onto a new version (issue-228,
[decision-084](/decisions/decision-084)).

```bash
the-loop restart [--with-upgrade]
```

`restart` is [`stop`](/cli/commands/stop) then [`start`](/cli/commands/start): every
running service is stopped (regardless of `enabled` flags), then every enabled one is
started, with both halves reported per service.

## `--with-upgrade`

Between stop and start, upgrade the-loop's own CLI using the
[installer](/cli/commands/install) planner from issue-152 — the same plan
`the-loop upgrade cli` runs, rendered with the same step table. Scope is deliberately
the CLI distribution only: the plugin component edits harness settings files no service
restart needs. The upgrade lands in place (same interpreter/venv), so the services
`restart` then starts run the new code.

**A failed upgrade never leaves the system down**: the start half still runs on the
current version, and the failure is reported and lands in the event log
(`restart.completed` with `ok: false`).

## Over the API

`restart` is also `POST /api/v1/restart` (body `{"withUpgrade": bool}`), which is how
the [dashboard](/capabilities/control-plane) or an operator's script bounces a running
deployment. The service cannot stop itself synchronously and still answer, so the API
**schedules**: it spawns a detached `the-loop restart` (fixed argv — nothing from the
request reaches the command line except the one boolean) and answers at once with the
spawned pid and its logfile (`<state.root>/logs/restart.out`). The request and the
completion both land in the [event log](/cli/commands/events) (`restart.scheduled`,
`restart.completed`).

The endpoint is deliberately **not** an MCP tool: it tears down the very transport an
MCP client is speaking over mid-call, and `--with-upgrade` reaches the installer — an
agent must not be able to replace the code it is judged by.

## See also

- [`start`](/cli/commands/start) · [`stop`](/cli/commands/stop) ·
  [`status`](/cli/commands/status)
- [`upgrade`](/cli/commands/upgrade) — the full installer, including the plugin
  component and `--dry-run`.
