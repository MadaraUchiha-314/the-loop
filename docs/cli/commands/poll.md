# `poll`

Pull-based ingress for hosts a webhook cannot reach — behind NAT or a firewall, a laptop,
infrastructure with no inbound route.

```bash
the-loop poll start [--interval 60] [--once] [--max-retries 3] \
                    [--state-file .the-loop/sessions/poll-state.json] \
                    [--pidfile .the-loop/poll.pid]
the-loop poll stop  [--pidfile .the-loop/poll.pid]
```

Every `--interval` seconds it asks each configured **provider** for the label-gated work
items in its scope, and drives them through the **same** routing, dispatch and session stack
the webhook receiver uses. Spawning, one-session-per-work-item, the `tmux` runner, harness
adapters and prompt templates are all reused unchanged.

## `start`

| Flag | Default | Meaning |
|------|---------|---------|
| `--interval` | [`polling.intervalSeconds`](/config/cli/polling-options#intervalseconds) | Seconds between cycles. |
| `--once` | off | Run a single cycle and exit — for a cron job or systemd timer. |
| `--max-retries` | [`polling.maxRetries`](/config/cli/polling-options#maxretries) | Per-event delivery attempts before giving up. |
| `--state-dir` | `<state.root>/portable` | Portable work-item records — the cross-poll, cross-restart comment dedup lives in each item's `poll` section ([state on disk](/cli/state)). |
| `--pidfile` | `<state.root>/poll.pid` | Where the PID is recorded, for `stop`. |

Without `--once` it loops until `poll stop` (or SIGINT/SIGTERM), writing a pidfile like the
receiver.

## `stop`

| Flag | Default | Meaning |
|------|---------|---------|
| `--pidfile` | `<state.root>/poll.pid` | The pidfile written by `start`. |

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
- **Spawns tmux sessions** when [`routing.runner: tmux`](/config/cli/routing-options#runner)
  — attach with `the-loop sessions attach --work-item github:OWNER/REPO#N`.
- **Retries.** A spawn or comment forward whose dispatch keeps failing is retried each cycle
  up to `--max-retries`; after that the poller logs a terminal failure (`poll.spawn_failed` /
  `poll.comment_failed`) and ignores the event until new activity re-arms it. An in-flight
  dispatch is not counted as a failed attempt.

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
The poller spawns only for items authored by a login in
[`routing.authorizedUsers`](/config/cli/routing-options#authorizedusers), and forwards only
comments from authorized authors. Everything else is ignored. CLI config only, **no**
fallback to any repository's harness config; an **empty** list fails closed with a warning.
[decision-023](/decisions/decision-023).
:::

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
[decision-022](/decisions/decision-022).

## Observability

Cycle summaries, spawns, forwarded comments and provider/item errors are appended to the
same [event log](/config/cli/observability-options#event-log) as the receiver:

```bash
the-loop events --source poll
```

## See also

- [Polling options](/config/cli/polling-options) · [Routing options](/config/cli/routing-options)
- [`gh-webhook`](/cli/commands/gh-webhook) — the push-based ingress.
