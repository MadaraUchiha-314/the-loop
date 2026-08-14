# `start`

Bring the-loop up: one command that reads the [CLI config](/config/cli/) and starts,
detached, **every service it enables** (issue-228,
[decision-084](/decisions/decision-084)).

```bash
the-loop start
```

| Service | Enabled by | Default |
|---------|-----------|---------|
| Control-plane service (REST + dashboard) | [`service.enabled`](/config/cli/service-options#enabled) | **on** |
| MCP endpoint (`/mcp`, mounted on the service) | [`service.mcp.enabled`](/config/cli/service-options#mcp-enabled) | **on** |
| GitHub webhook receiver | [`webhooks.ghWebhook.enabled`](/config/cli/webhook-options#enabled) | off |
| Poller | [`polling.enabled`](/config/cli/polling-options#enabled) | off |

The ingresses are explicit opt-ins: a config that merely *describes* a receiver or a
polling source must not open a port or start a loop. `start` prints one line per
service — `started`, `already-running` (start is idempotent), `disabled` (naming the
key that enables it), `misconfigured` (an enabled poller with no
`polling.sources`), or `failed` (pointing at the service's logfile) — and exits 0 only
when every enabled service came up. One service failing never hides the others'
outcomes.

```console
$ the-loop start
service     started          [enabled]  started at http://127.0.0.1:4114; /mcp exposed
gh-webhook  disabled         [disabled]  webhooks.ghWebhook.enabled is false
poller      started          [enabled]  spawned pid 24913; logging to .the-loop/logs/poller.out
```

Each daemon is spawned detached (its own session, output to its logfile under
[`state.root`](/cli/state)) and `start` waits for the proof that it is genuinely up —
the service's `/health`, a daemon's pidfile lock — before reporting success.

## Foreground and cron forms

`start` composes daemons; it does not host one in your shell. For a supervisor
(systemd `Type=simple`) or a cron job, run the daemon entry point directly:

```bash
python -m the_loop.daemon_entry poller           # foreground run loop
python -m the_loop.daemon_entry poller --once    # one poll cycle and exit (cron)
python -m the_loop.daemon_entry gh-webhook       # foreground receiver
```

These replace the removed `the-loop poll start [--once]`; the run loop itself is
unchanged (lock, dependency checks, heartbeat, config hot-reload).

## See also

- [`stop`](/cli/commands/stop) · [`status`](/cli/commands/status) ·
  [`restart`](/cli/commands/restart)
- [The control-plane service](/cli/service) and [the webhook receiver](/cli/receiver) —
  what each service is and how to talk to it (`/mcp`, verification, guards). The
  granular `service`/`gh-webhook`/`poll` commands are gone (owner review on PR #229):
  this one surface is the lifecycle.
