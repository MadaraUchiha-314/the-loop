# `gh-webhook`

The GitHub webhook receiver: verifies deliveries, maps each to a work item, and routes it
to the harness session working that item.

```bash
the-loop gh-webhook start [--host 127.0.0.1] [--port 8787] [--path /gh-webhook] \
                          [--pidfile .the-loop/gh-webhook.pid] \
                          [--secret-env THE_LOOP_GH_WEBHOOK_SECRET] \
                          [--route | --no-route]
the-loop gh-webhook stop  [--pidfile .the-loop/gh-webhook.pid]
```

Defaults come from [`webhooks.ghWebhook`](/config/cli/webhook-options) in the CLI config.
**Flags always override.**

## `start`

| Flag | Default | Meaning |
|------|---------|---------|
| `--host` | [`webhooks.ghWebhook.host`](/config/cli/webhook-options#host) | Interface to bind. |
| `--port` | [`…port`](/config/cli/webhook-options#port) | Listen port. |
| `--path` | [`…path`](/config/cli/webhook-options#path) | HTTP path served. |
| `--secret-env` | [`…secretEnv`](/config/cli/webhook-options#secretenv) | Env var holding the HMAC secret. |
| `--pidfile` | [`…pidfile`](/config/cli/webhook-options#pidfile) | Where the PID is recorded, for `stop`. |
| `--route` / `--no-route` | [`…routing.enabled`](/config/cli/routing-options#enabled) | Whether to dispatch, or only verify and log. |

## `stop`

| Flag | Default | Meaning |
|------|---------|---------|
| `--pidfile` | [`…pidfile`](/config/cli/webhook-options#pidfile) | The pidfile written by `start`. |

## Verification

The `X-Hub-Signature-256` HMAC is verified whenever the secret env var is set:

```bash
export THE_LOOP_GH_WEBHOOK_SECRET='the same secret you gave GitHub'
the-loop gh-webhook start
```

The secret is read from the **environment**, never from a flag, so it cannot leak into a
process listing — and never from the config file, so it cannot be committed.

::: warning Unset means unverified
With the variable unset the receiver starts, warns, and accepts unsigned deliveries. Anyone
who can reach the port can post an event.
:::

`GET /health` returns `200 ok` unconditionally — use it for a readiness probe.

## Routing

With `--route`, each verified event is mapped to the work item(s) it concerns and delivered
to that item's registered session:

- **Extraction** — issue/PR number, the `issue-<n>` PR head-branch convention, closing
  keywords, and the PRs behind `workflow_run` / `check_*` events.
- **Dedup** — on `X-GitHub-Delivery`, through a bounded LRU
  ([`dedupCacheSize`](/config/cli/routing-options#dedupcachesize)), so GitHub's redeliveries
  are processed at most once.
- **Dispatch** — the rendered prompt is pasted into the matched session's tmux-hosted
  TUI (respawning it first when it has died), one event
  at a time per session, in parallel across sessions
  ([`maxConcurrentDispatches`](/config/cli/routing-options#maxconcurrentdispatches)).
- **Unmatched** events follow
  [`spawnOnUnmatched`](/config/cli/routing-options#spawnonunmatched).

Design: [`docs/specs/issue-15/design.md`](/specs/issue-15/design) ·
[decision-016](/decisions/decision-016).

## Guards

Both run before dispatch, in this order. See [concepts](/cli/concepts#guards).

### Self-reply guard

the-loop posts under your own credentials, so authorship cannot distinguish its comments
from yours. Every comment, review and reply it writes carries an embedded marker, and a
marker-carrying event is dropped before dispatch **regardless of actor** — so the-loop's own
reply never resumes the session that wrote it.
[decision-031](/decisions/decision-031).

### Authorized-actor guard

::: danger Required, no fallback, fails closed
The receiver acts only on actions by logins in
[`routing.authorizedUsers`](/config/cli/routing-options#authorizedusers) — CLI config only,
with **no** fallback to any repository's harness config. Comments, reviews, and issue/PR
labels and opens from anyone else are dropped before dispatch. An **empty** list fails
closed, with a warning at startup.

CI and system events, which carry no human instructions, still pass; and a `closed` event
still auto-closes that item's own session. Each operator runs their own instance for their
own logins. [decision-023](/decisions/decision-023).
:::

## Execution control

A comment carrying a declared [control keyword](/config/cli/routing-options#execution-control)
is interpreted by the-loop and **not** forwarded to the agent. Parsing happens strictly
after both guards, so it is never a second, weaker way in. With the default
`requireStartCommand: true`, a labelled work item waits for an authorized user's explicit
start before anything spawns.

## Config hot-reload

While the receiver runs, edits to `routing` and `events` are picked up on the **next
received event** — no restart. The soft policy swaps live: events filter, label, spawn
policy, harness, per-harness args, prompt templates. The dedup cache, per-session
queues and registry are preserved.

Infrastructural settings still need a restart: `host`, `port`, `path`, `secretEnv`,
`maxConcurrentDispatches`, `dedupCacheSize`, `registryDir`, `webTerminal`. An invalid edit is
logged and the previous config kept.

## Observability

Every receive, reject, route, dispatch, spawn and close decision is appended to the
[event log](/config/cli/observability-options#event-log). Query it with
[`the-loop events --source gh-webhook`](/cli/commands/events).

## See also

- [Webhook options](/config/cli/webhook-options) · [Routing options](/config/cli/routing-options)
- [polling](/config/cli/polling-options) — the same dispatch stack, pull-based; started by [`the-loop start`](/cli/commands/start).
- [webhook triggers](/capabilities/webhook-triggers) — the capability doc.
