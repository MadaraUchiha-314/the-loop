# `stop`

Stop every running the-loop service — poller, webhook receiver, control-plane
service — in reverse start order (issue-228,
[decision-084](/decisions/decision-084)).

```bash
the-loop stop
```

`stop` deliberately **ignores the `enabled` flags**: a service you disabled *after*
starting it must still be stoppable. Each stop is the honest kind the daemons have had
since issue-159 — the pid is signalled only when the pidfile's lock proves a live
process holds it (never a stale pid that could belong to a stranger), and success is
reported only once the lock is released, so a scripted `the-loop stop && the-loop
start` cannot overlap the shutdown it just asked for.

```console
$ the-loop stop
poller      stopped          [enabled]  stopped poller (pid 24913)
gh-webhook  not-running      [disabled]  gh-webhook is not running
service     stopped          [enabled]  stopped (pid 24846)
```

Idempotent in both directions: stopping a stopped system exits 0 with `not-running`
rows. The exit code is non-zero only when something that *was* running failed to exit
within the timeout.

## See also

- [`start`](/cli/commands/start) · [`status`](/cli/commands/status) ·
  [`restart`](/cli/commands/restart)
