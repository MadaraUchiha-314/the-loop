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
| [Standing sessions](/capabilities/standing-sessions) | [`standingSessions.enabled`](/config/cli/standing-sessions-options#enabled) | off |

The ingresses are explicit opt-ins: a config that merely *describes* a receiver or a
polling source must not open a port or start a loop. `start` prints one line per
service — `started`, `hosted` (see below), `already-running` (start is idempotent),
`disabled` (naming the key that enables it), `misconfigured` (an enabled poller with no
`polling.sources`), or `failed` (pointing at the service's logfile) — and exits 0 only
when every enabled service came up. One service failing never hides the others'
outcomes.

## One process by default

With the service enabled and
[`service.hostIngresses`](/config/cli/service-options#hostingresses) at its default
(`true`, [issue-231](https://github.com/MadaraUchiha-314/the-loop/issues/231)), `start`
boots **one process**: the service, which runs the enabled ingresses as background
threads inside its own lifespan. Each hosted ingress still holds its own pidfile lock —
under the service's pid — so `status`, `stop` and the daemons API answer unchanged, and
an ingress already running standalone is skipped with a warning, never fought over.

```console
$ the-loop start
service     started          [enabled]  started at http://127.0.0.1:4114; /mcp exposed
gh-webhook  hosted           [enabled]  in the service process (pid 24846)
poller      hosted           [enabled]  in the service process (pid 24846)
```

Set `hostIngresses: false` to keep every enabled service in its own process (fault
isolation). Then each daemon is spawned detached (its own session, output to its
logfile under [`state.root`](/cli/state)):

```console
$ the-loop start
service     started          [enabled]  started at http://127.0.0.1:4114; /mcp exposed
gh-webhook  disabled         [disabled]  webhooks.ghWebhook.enabled is false
poller      started          [enabled]  spawned pid 24913; logging to .the-loop/logs/poller.out
```

In either mode `start` waits for the proof that a service is genuinely up — the
service's `/health`, an ingress's pidfile lock — before reporting success.

## Standing sessions

With [`standingSessions.enabled`](/config/cli/standing-sessions-options#enabled), `start`
also brings up every declared session whose `autoStart` is true — **after** the service,
so anything they run can reach it — and prints them in their own section:

```console
$ the-loop start
service     started          [enabled]  started at http://127.0.0.1:4114; /mcp exposed
gh-webhook  hosted           [enabled]  in the service process (pid 24846)
poller      hosted           [enabled]  in the service process (pid 24846)
standing sessions:
supervisor  resumed          resumed loop-standing-supervisor (claude 0f3a…)
```

A session whose pane is already alive is `already-running` and is not touched; one with a
recorded conversation is **resumed**, not restarted from nothing. See
[`standing`](/cli/commands/standing).

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
