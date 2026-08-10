# Evidence — integration and the abuse cases (T6, T7)

Row T6 of [`testing-plan.md`](../testing-plan.md): a **real** detached poller, spawned as a
subprocess against a temporary `state.root`, interrogated through `/proc`. Mocking
`os.fork` would have proved only that we called it; every claim below is a statement about
the running system.

No network is reached (the `gh` on `PATH` is a stub that lists nothing), no session is
spawned (`routing.enabled: false`), and each test kills what it spawned in a `finally`.

## The run

```text
$ uv run --project cli python -m pytest -v cli/tests/test_poll_daemon_integration.py
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
collected 7 items

test_a_daemonized_poller_owns_its_session_pidfile_and_log PASSED          [ 14%]
test_a_daemonized_poller_outlives_the_shell_that_started_it PASSED        [ 28%]
test_the_starter_leaves_no_zombie_behind PASSED                           [ 42%]
test_a_daemonized_start_refuses_when_a_poller_already_holds_the_lock PASSED [ 57%]
test_a_daemonized_start_reports_a_startup_failure_to_its_caller PASSED    [ 71%]
test_a_stale_pidfile_is_removed_by_the_next_daemonized_start PASSED       [ 85%]
test_status_reports_a_running_poller_its_pid_and_its_last_cycle PASSED    [100%]

7 passed in 12.51s
```

| Scenario | Requirement | What it asserts against the live process |
|---|---|---|
| A daemonized poller owns its pidfile and its logfile | R1.1, R2.1, R3.1, R3.5 | the reported pid holds the pidfile's flock; its ppid is not the starter's; `sid == pgid` and both differ from the test runner's group; the logfile is receiving the startup lines |
| A daemonized poller outlives the shell that started it | R1.2 | the daemon has left the starter's group *and* session, and is still alive with its lock after that whole group is `SIGKILL`ed |
| The intermediate child is reaped | R1.1 | the starter leaves no zombie behind |
| A daemonized start refuses when a poller already holds the lock | R3.3, **T7** | exit `1`, the holding pid named, the running poller undisturbed |
| A daemonized start reports a startup failure to its caller | R3.4 | with no polling sources: exit `1`, "the poller did not come up", the logfile named, no lock left held, and the real reason in the log |
| A stale pidfile is removed by the next start | R3.2, **T7** | a planted pid (999999) is gone, the pidfile names the new daemon, and the removal is logged |
| `poll status` reports a running poller, its pid and its last cycle | R4.1–R4.3, R4.5 | exit `0` with `running: true` and that pid while up; exit `1` with the cycle still reported once it has stopped |

## The same thing by hand

The behaviour an operator actually sees, run end to end in a scratch directory. Paths and
pids are from that run; nothing here is edited except the removal of a temporary path
prefix.

```console
$ the-loop poll start --daemon
poller started (pid 1520); logging to .the-loop/logs/poller.out

$ ps -o pid=,ppid=,pgid=,sess=,tty=,comm= -p 1520
 1520     1  1519  1519 ?        python3
(the invoking shell: pid 1157, pgid 1157)
```

Three facts in one line of `ps`, and they are the whole ticket: **ppid 1** — reparented to
init, so no parent teardown reaches it; **sess 1519 ≠ 1157** — its own session, not the
shell's; **tty `?`** — no controlling terminal to lose. The daemon (1520) is the child of
the session leader (1519), which is what the second fork buys.

```console
$ the-loop poll status
poller:     running (pid 1520)
pidfile:    .the-loop/poll.pid
logfile:    .the-loop/logs/poller.out
started:    2026-08-10T04:51:44Z (3s ago)
last cycle: 2026-08-10T04:51:46Z (1s ago) — 0 item(s), 0 spawn(s), 0 comment(s) forwarded
exit=0

$ the-loop poll start --daemon          # a second one, against the same state
another poller is already running (pid 1520, pidfile .the-loop/poll.pid); stop it first with `the-loop poll stop`
exit=1

$ the-loop poll stop
sent SIGTERM to poll process (pid 1520); waiting for it to exit
poll process (pid 1520) stopped

$ the-loop poll status
poller:     not running
pidfile:    .the-loop/poll.pid
logfile:    .the-loop/logs/poller.out
started:    2026-08-10T04:51:44Z (4s ago)
last cycle: 2026-08-10T04:51:46Z (2s ago, before it stopped) — 0 item(s), 0 spawn(s), 0 comment(s) forwarded
exit=1
```

The exit codes are the point of the last two: `0` while it is up, `1` once it is not, with
the last cycle still reported. That is the health check a keepalive is built on.

The log the daemon kept — the thing that went missing in the incident this ticket is
about:

```text
$ tail -5 .the-loop/logs/poller.out
2026-08-10 04:51:44,771 INFO the-loop.poll poll: github octo/repo every 2s (spawnOnUnmatched=never, state=.the-loop/portable)
2026-08-10 04:51:44,771 INFO the-loop.poll a labelled work item is armed, not started: an authorized user starts it by commenting 'the-loop start' …
2026-08-10 04:51:44,776 INFO the-loop.poll poll cycle: 0 item(s), 0 spawn(s), 0 comment(s) forwarded
2026-08-10 04:51:46,780 INFO the-loop.poll poll cycle: 0 item(s), 0 spawn(s), 0 comment(s) forwarded
2026-08-10 04:51:48,338 INFO the-loop.poll received signal 15, stopping poller
```

The heartbeat behind the progress lines:

```json
{
  "pid": 1520,
  "startedAt": "2026-08-10T04:51:44Z",
  "lastCycleAt": "2026-08-10T04:51:46Z",
  "intervalSeconds": 2,
  "lastCycle": {
    "itemsSeen": 0, "spawns": 0, "commentsForwarded": 0,
    "closures": 0, "failures": 0, "errors": 0, "interrupted": false
  }
}
```

And the refusal that keeps `--once` honest for cron:

```console
$ the-loop poll start --daemon --once
--daemon and --once are contradictory: a single cycle has nothing to detach for, and
detaching would hide its exit code from the cron job that asked for it. Use one or the other.
exit=2
```
