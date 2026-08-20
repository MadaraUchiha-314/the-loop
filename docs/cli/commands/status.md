# `status`

One report for the whole system: per service, whether the config enables it, whether it
is running (and as which pid), and the poller's progress (issue-228,
[decision-084](/decisions/decision-084)).

```bash
the-loop status [--format text|json]
```

```console
$ the-loop status
service     running (pid 24846) [enabled] — http://127.0.0.1:4114, healthy
gh-webhook  not running [disabled]
poller      running (pid 24913) [enabled]
            started:    2026-08-14T20:41:12Z (2m ago)
            last cycle: 2026-08-14T20:43:02Z (10s ago) — 5 item(s), 1 spawn(s), 0 comment(s) forwarded
```

An ingress running [inside the service](/config/cli/service-options#hostingresses)
(issue-231) says so — same lock-based liveness, its lock is simply held by the
service's pid — and the JSON rows carry it as `"hosted": true`:

```console
$ the-loop status
service     running (pid 24846) [enabled] — http://127.0.0.1:4114, healthy
gh-webhook  running (hosted in the service, pid 24846) [enabled]
poller      running (hosted in the service, pid 24846) [enabled]
            ...
```

Two properties carried over from the removed `poll status` (issue-191/205):

- **Liveness and the pid come from the pidfile's lock, never from a file's claim.** A
  forged or leftover heartbeat cannot make a dead poller look alive, and a stale
  pidfile is reported as *not running* — and left alone; `status` is read-only.
- **The heartbeat is enrichment.** An absent or unreadable one loses the progress
  lines, never the liveness answer.

[Standing sessions](/capabilities/standing-sessions) get their own section, and count
toward the exit code — but only the ones [`start`](/cli/commands/start) **would have
started** (the block enabled, and the entry's `autoStart` true). One declared without
`autoStart`, or one that is only in the registry because you started it by hand, is
reported without deciding the answer.

```console
$ the-loop status
service     running (pid 24846) [enabled] — http://127.0.0.1:4114, healthy
...
standing sessions:
supervisor  running [declared]
triage      not running [declared, not auto-started]
```

**The exit code is the health check** ([R3.3](https://github.com/MadaraUchiha-314/the-loop/issues/228)):
0 iff every **enabled** service is running, so `the-loop status || …` is the keepalive
primitive. `--format json` emits the same facts as one document (per-service rows plus
`ok`), including the service's URL, its `/health` answer, whether `/mcp` is exposed,
and the poller's last-cycle counters.

## See also

- [`start`](/cli/commands/start) · [`stop`](/cli/commands/stop) ·
  [`restart`](/cli/commands/restart)
- [`events`](/cli/commands/events) — why something is not running.
