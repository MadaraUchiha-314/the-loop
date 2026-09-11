# Keeping it running

::: danger `the-loop start` is not a supervisor
It starts each enabled service **once** and returns. Nothing restarts a service that
later dies — the package ships no systemd unit, no cron entry, no watchdog and no
`--restart` flag. **Supervision is yours**, and this page is the unit to copy.
:::

That sentence exists because its absence cost someone 17 hours
([issue-339](https://github.com/MadaraUchiha-314/the-loop/issues/339)): a package upgrade
restarted the service, the poller did not come back, and nothing noticed until a human
wondered why comments had stopped arriving. Two of the three reasons that stayed invisible
are fixed — `/api/v1/health` now reports a poller that is missing, and an ingress that
fails to start writes an event — but **something still has to restart it**, and that
something is your init system.

## What to supervise

One process, whatever your config enables. With
[`service.hostIngresses`](/config/cli/service-options#hostingresses) at its default, the
control-plane service hosts the [poller](/config/cli/polling-options), the
[webhook receiver](/cli/receiver) and the Slack listener as threads of its own process, so
supervising **the service** supervises all of them. Set it `false` and you have one
process per service, each with its own unit.

## The systemd user unit

```ini
# ~/.config/systemd/user/the-loop.service
[Unit]
Description=the-loop control plane
After=network-online.target

[Service]
Type=simple
# The config this unit means, named explicitly. The working directory is NOT how the
# config or the state root is found (decision-119) — name the file and nothing is
# ambiguous.
Environment=THE_LOOP_CLI_CONFIG=%h/.the-loop/cli-config.yaml
ExecStart=%h/.local/bin/the-loop start
ExecStop=%h/.local/bin/the-loop stop
RemainAfterExit=yes
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

```sh
systemctl --user daemon-reload
systemctl --user enable --now the-loop
loginctl enable-linger "$USER"   # so it survives logout
```

`the-loop start` returns once every enabled service is up, which is why the unit is
`Type=simple` with `RemainAfterExit=yes`: systemd tracks the *unit*, and `Restart=always`
re-runs `start` if it ever exits non-zero — which it does when an enabled service did not
come up.

Prefer systemd to supervise the process directly? Run the service in the foreground
instead, and drop `RemainAfterExit`:

```ini
ExecStart=%h/.local/bin/python3 -m the_loop.api.serve
```

## The cron form

A poller that runs one cycle and exits, for a box with no long-lived process:

```cron
*/5 * * * * THE_LOOP_CLI_CONFIG=$HOME/.the-loop/cli-config.yaml \
  /home/you/.local/bin/python3 -m the_loop.daemon_entry poller --once \
  >> $HOME/.the-loop/logs/poller.out 2>&1
```

One cycle takes the same single-instance lock a daemon does, so two overlapping
invocations cannot interleave — the second exits rather than double-forwarding a comment.

## The health check to watch

```console
$ curl -s http://127.0.0.1:4114/api/v1/health | jq .
{
  "status": "ok",
  "version": "13.12.0",
  "configPath": "/home/you/.the-loop/cli-config.yaml",
  "stateRoot": "/home/you/.the-loop",
  "ingresses": [
    {"name": "poller", "enabled": true, "running": true, "detail": ""},
    {"name": "gh-webhook", "enabled": false, "running": false, "detail": ""},
    {"name": "slack-listener", "enabled": false, "running": false, "detail": ""}
  ]
}
```

Alert on **`status != "ok"`**, not on the HTTP code. The code is always 200 while the
service answers — that is deliberate, because it is also the liveness probe the CLI's
auto-start loop reads, and a 503 would have every unrelated command spawn a second
service. `degraded` means an ingress your config *enables* is holding no lock, and the
row's `detail` names the config key and the pidfile:

```json
{"name": "poller", "enabled": true, "running": false,
 "detail": "polling.enabled is true but nothing holds /home/you/.the-loop/poll.pid"}
```

`the-loop status` answers the same question on a terminal, and adds the two lines that
say which files it is answering **about**:

```console
$ the-loop status
config      /home/you/.the-loop/cli-config.yaml
state       /home/you/.the-loop
service     running (pid 24846) [enabled] — http://127.0.0.1:4114, healthy
poller      running (hosted in the service, pid 24846) [enabled]
            last cycle: 2026-09-11T09:14:02Z (12s ago) — 18 item(s), 0 spawn(s), …
```

A `conflict` line above them means a second state root also holds a heartbeat — usually
state left behind by a pre-13.12.0 daemon started from another directory. the-loop names
it and reports on the one it resolved; moving or deleting the other is yours to do, while
nothing is running.

## When something did not come up

```sh
the-loop events --source service | tail
```

An enabled ingress that failed to start records `ingress.hosted_failed` with the reason —
a lock another process holds, an enabled poller with no `polling.sources` or no top-level
`repositories`, a Slack token variable that is not set. The service keeps serving through it on purpose: the API being
up is what lets you read the reason.

## See also

- [The control-plane service](/cli/service) — what it is and how it is configured
- [State on disk](/cli/state) — what the daemon writes, and where
- [`the-loop start`](/cli/commands/start) · [`status`](/cli/commands/status) ·
  [`restart`](/cli/commands/restart)
- [decision-119](/decisions/decision-119) — one state root per configuration
