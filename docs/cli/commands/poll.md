# `poll`

Pull-based ingress for hosts a webhook cannot reach — behind NAT or a firewall, a laptop,
infrastructure with no inbound route.

```bash
the-loop poll start  [--interval 60] [--once] [--max-retries 3] \
                     [--daemon | --foreground] \
                     [--logfile .the-loop/logs/poller.out] \
                     [--state-dir .the-loop/portable] \
                     [--pidfile .the-loop/poll.pid] \
                     [--status-file .the-loop/poll-status.json]
the-loop poll stop   [--pidfile .the-loop/poll.pid] [--timeout 30]
the-loop poll status [--pidfile …] [--logfile …] [--status-file …] [--format text|json]
```

Every `--interval` seconds it asks each configured **provider** for the label-gated work
items in its scope, and drives them through the **same** routing, dispatch and session stack
the webhook receiver uses. Spawning, one-session-per-work-item, tmux hosting, harness
adapters and prompt templates are all reused unchanged.

## `start`

| Flag | Default | Meaning |
|------|---------|---------|
| `--interval` | [`polling.intervalSeconds`](/config/cli/polling-options#intervalseconds) | Seconds between cycles. |
| `--once` | off | Run a single cycle and exit — for a cron job or systemd timer. |
| `--max-retries` | [`polling.maxRetries`](/config/cli/polling-options#maxretries) | Per-event delivery attempts before giving up. |
| `--daemon` / `--foreground` | `--foreground` | Detach and run as a real daemon, or stay in the foreground. One setting; the last flag on the line wins. |
| `--logfile` | `<state.root>/logs/poller.out` | Where a **daemonized** poller's stdout/stderr go. Ignored in the foreground, where your shell owns them. |
| `--state-dir` | `<state.root>/portable` | Portable work-item records — the cross-poll, cross-restart comment dedup lives in each item's `poll` section ([state on disk](/cli/state)). |
| `--pidfile` | `<state.root>/poll.pid` | Where the PID is recorded, and the file the single-instance lock is held on. |
| `--status-file` | `<state.root>/poll-status.json` | The heartbeat [`status`](#status) reads. |

Without `--once` it loops until `poll stop` (or SIGINT/SIGTERM), writing a pidfile like the
receiver.

### Foreground or daemon?

`start` runs in the **foreground** by default, because that is what a supervisor wants: a
systemd `Type=simple` unit and a `--once` cron job both need the process they launched to
be the process that does the work.

Everywhere else — a laptop, an SSH session, a tmux pane, another tool's background task —
use `--daemon`. It does the five things the incantation used to:

```bash
# before
setsid nohup the-loop poll start --pidfile … >> .the-loop/logs/poller.out 2>&1 &
# now
the-loop poll start --daemon
```

| It does | So that |
|---|---|
| double-fork + `setsid` | the poller owns its session and process group, has no controlling terminal, and is reparented to init — **no parent teardown can take it down** |
| redirects stdout/stderr to `--logfile` (append), stdin to `/dev/null` | a detached poller can never *stop* logging because of how it was started |
| writes the pidfile after the final fork | the recorded pid is the process that is actually running |
| waits until the daemon is genuinely up before returning | `poll start --daemon && poll status` cannot race its own daemon |
| keeps the working directory | every relative path — the CLI config, `state.root`, the workspace — still resolves as you typed it |

A failed start is reported to **your terminal**, not to the log: a conflicting `--once`,
an unopenable logfile and a lock another poller holds are all checked before forking, and
anything that fails after it (a missing dependency, a bad provider) comes back over the
startup handshake as `the poller did not come up … See <logfile>` with exit `1`.

The logfile is never rotated by the-loop — point `logrotate` at it on a long-lived host
([state on disk](/cli/state#poller-log-root-logs-poller-out)).

::: info Supervision is still not the poller's job
`--daemon` makes a poller survive the *shell* that started it. It does not survive a
reboot, a suspend, or being `SIGKILL`ed — that is systemd, cron or a keepalive script, and
`poll status`'s exit code is the health check to build one on.
:::

**One poller per state root.** `start` takes an exclusive lock on the pidfile and holds it
for the whole run — `--once` included, so two overlapping cron invocations cannot interleave.
A second `start` against the same state refuses, names the pid holding it, and exits `1`
without touching the ledger (`poller.blocked` in the event log). Two pollers configured with
different `state.root` values are independent and both run. A pidfile left behind by a crash
is *unlocked*, so the next `start` reports it as stale, removes it and takes a fresh one — a
`SIGKILL` never needs manual cleanup.

## `stop`

| Flag | Default | Meaning |
|------|---------|---------|
| `--pidfile` | `<state.root>/poll.pid` | The pidfile written by `start`. |
| `--timeout` | `30` | Seconds to wait for the poller to actually exit. |

`stop` sends `SIGTERM` and then **waits until the poller has exited**, so `poll stop &&
poll start` cannot overlap the shutdown it just asked for. It signals a pid only when the
lock proves a poller holds it: a pidfile left behind by a killed poller is reported as stale
and removed, and nothing is signalled — previously that pid was signalled blindly, which on a
busy host meant `SIGTERM` to whichever process had inherited it. A poller still draining when
`--timeout` runs out is reported and `stop` exits `1` rather than claiming a success that has
not happened.

## `status`

| Flag | Default | Meaning |
|------|---------|---------|
| `--pidfile` | `<state.root>/poll.pid` | The lock that answers "is one running?". |
| `--logfile` | `<state.root>/logs/poller.out` | Reported so you know where to look next. |
| `--status-file` | `<state.root>/poll-status.json` | The heartbeat the progress lines come from. |
| `--format` | `text` | `text` or `json` — the same facts either way. |

```console
$ the-loop poll status
poller:     running (pid 48213)
pidfile:    .the-loop/poll.pid
logfile:    .the-loop/logs/poller.out
started:    2026-08-10T09:58:03Z (44m ago)
last cycle: 2026-08-10T10:42:00Z (2m ago) — 5 item(s), 1 spawn(s), 0 comment(s) forwarded
```

**It exits `0` when a poller is running and `1` when none is**, which is what makes it a
health check rather than a report: `the-loop poll status >/dev/null || the-loop poll start
--daemon` is a complete keepalive.

Liveness comes from the **lock**, never from the heartbeat — the only formulation immune to
pid reuse, and the only one a file cannot forge. So a stopped poller reads:

```console
$ the-loop poll status
poller:     not running
pidfile:    .the-loop/poll.pid (stale — pid 48213 is not running)
logfile:    .the-loop/logs/poller.out
started:    2026-08-10T09:58:03Z (3h ago)
last cycle: 2026-08-10T10:42:00Z (2h ago, before it stopped) — 5 item(s), 1 spawn(s), 0 comment(s) forwarded
```

`status` **reports** a stale pidfile without removing it — a read-only command that mutates
is a trap for whoever ran it to find out what was there. `start` and `stop` remove it, and
they are the commands you run next.

A poller with no heartbeat yet — one started before this file existed, or one whose
heartbeat you deleted — still reports liveness and pid; only the progress lines are
missing, and it says so.

## Provider-agnostic

The poller core and its CLI carry **no** GitHub knobs. What gets polled is defined purely by
[`polling.sources`](/config/cli/polling-options#sources) — each entry names a `provider`
(GitHub ships; the seam admits others):

```yaml
polling:
  intervalSeconds: 60
  sources:
    - provider: github
      repos: [octo/repo]         # REQUIRED — no fallback to any repo's harness config
      monitor: { issues: true, pullRequests: true }
      label: ""                  # empty = reuse routing.autoExecuteLabel
```

GitHub is reached only through your own authenticated `gh` — the daemon holds no token.

## Behaviour

- **Label-gated.** Only items carrying the configured label are polled. A source's `label`
  defaults to [`routing.autoExecuteLabel`](/config/cli/routing-options#autoexecutelabel), so
  one label drives both ingresses.
- **No duplicate sessions.** A session is spawned for a labelled item only when the registry
  has none. A live session is never doubled — the registry is the source of truth — so a work
  item maps to exactly one session, the same one on later polls.
- **New comments** are forwarded exactly once, deduped across cycles **and restarts** via
  `--state-file`. The pre-existing thread is *baselined* on first sight, not replayed.
- **Spawns tmux sessions** — every spawned session is hosted in a named tmux session.
  Attach with `the-loop sessions attach --work-item github:OWNER/REPO#N`.
- **Retries.** A spawn or comment forward whose dispatch keeps failing is retried each cycle
  up to `--max-retries`; after that the poller logs a terminal failure (`poll.spawn_failed` /
  `poll.comment_failed`) and ignores the event until new activity re-arms it. An in-flight
  dispatch is not counted as a failed attempt.

### Stopping and restarting

Restarting is meant to be **invisible**: a poller that was stopped and started behaves like
one that never stopped. Four things make that true, on top of the durable per-item ledger.

- **One at a time.** The [single-instance lock](#start) is what stops two pollers from
  interleaving read-modify-write over the same records and re-forwarding each other's
  comments.
- **`stop` is true when it returns.** It waits for the process to exit (see [`stop`](#stop)),
  so a scripted restart is deterministic rather than lucky.
- **Progress is durable per work item.** Each item's record is written as soon as that item is
  done, not at the end of the cycle, so a `SIGKILL` mid-cycle loses the item in flight and
  nothing else.
- **A stop is honoured inside a cycle.** `SIGTERM` ends the cycle after the work item in
  flight rather than after every remaining item — each of which could otherwise block for up
  to [`dispatchTimeoutSeconds`](/config/cli/routing-options#dispatchtimeoutseconds). An
  interrupted cycle is marked `interrupted` in `poll.cycle`, and **skips closure
  reconciliation**: a partial listing is not evidence that the unlisted items ended, the same
  rule a failed listing already follows.
- **Restarts cost no retry budget.** Events still queued when the dispatcher shuts down are
  reported (`dispatch.abandoned`) and the attempts they spent are handed back
  (`poll.attempts_released`), so they are retried by the next start with the budget they
  started with instead of accumulating toward `--max-retries` across restarts.

### Closing finished work items

A listing only ever carries *open* items, so a closed issue or merged PR simply vanishes
from it. That absence is not proof, so the poller does not treat it as such:

After each **successful** listing it reconciles the registry against it. An active session
whose item is no longer listed is checked once upstream
(`gh api repos/…/issues/<n>`), and a genuinely closed or merged item is closed through the
same path a `closed` webhook takes — registry entry closed, tmux handled per
[`routing.tmux`](/config/cli/routing-options#tmux-keepsessiononclose), workspace cleaned.

It never closes on doubt: a **failed** listing skips reconciliation entirely, and an
unanswerable state query leaves the session running for the next cycle. Reopening an item
makes it first-sight again, so work restarts.

## Guards

Identical to the receiver's, and just as load-bearing — see [concepts](/cli/concepts#guards).

::: danger Required, no fallback, fails closed
The poller forwards only comments from authors in
[`routing.authorizedUsers`](/config/cli/routing-options#authorizedusers). Everything else is
ignored. CLI config only, **no** fallback to any repository's harness config; an **empty**
list fails closed with a warning. [decision-023](/decisions/decision-023).
:::

**Who opened the work item gates one thing: whether the poller starts work on it by
itself.** A poll listing carries an item's labels but not who applied them, so there is no
event actor for the item — spawning is gated on the item's author being authorized, *or* on
an authorized user having armed it (`the-loop start` / `the-loop contribute`, or
`the-loop sessions start`; a later `stop`/`pause`/`cleanup` disarms it again).

A **comment** is judged by its own author, always. So a maintainer can point the-loop at an
outside contributor's issue or PR with one comment, and the contributor still cannot steer
it — theirs is dropped by the same check as before. The spawned session is told in its
prompt that the work item's title, body and thread are untrusted content.
[decision-074](/decisions/decision-074).

While a spawn is being withheld — an unauthorized author, nobody having armed the item —
each cycle records `poll.unauthorized` naming that author. It stops as soon as the item is
armed.

The **self-reply guard** applies too: a comment the-loop itself posted is excluded from "new
comments" and cannot retrigger a spawn, even though it was posted under an authorized login.
[decision-031](/decisions/decision-031).

## Config

Ingress defaults come from [`polling`](/config/cli/polling-options). Dispatch behaviour is
reused from [`routing`](/config/cli/routing-options) in the same file.
Flags cover only the run loop.

**Hot reload:** edit `polling.sources` or `intervalSeconds` while it runs and the change is
picked up on the next cycle — no restart. An invalid edit is logged and the previous config
kept. The shared dispatch config still needs a restart.

Design: [`docs/specs/issue-34/design.md`](/specs/issue-34/design) ·
[decision-022](/decisions/decision-022) · [decision-072](/decisions/decision-072).

## Observability

Cycle summaries, spawns, forwarded comments and provider/item errors are appended to the
same [event log](/config/cli/observability-options#event-log) as the receiver:

```bash
the-loop events --source poll
```

## See also

- [Polling options](/config/cli/polling-options) · [Routing options](/config/cli/routing-options)
- [`gh-webhook`](/cli/commands/gh-webhook) — the push-based ingress.
