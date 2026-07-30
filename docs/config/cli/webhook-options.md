---
configBase: webhooks.ghWebhook
---

# Webhook options

Options under `webhooks.ghWebhook` — the GitHub webhook receiver started by
[`the-loop gh-webhook start`](/cli/commands/gh-webhook). They configure the **listener**;
what it does with an event it accepts is [routing](/config/cli/routing-options).

```yaml
webhooks:
  ghWebhook:
    host: 127.0.0.1
    port: 8787
    path: /gh-webhook
    secretEnv: THE_LOOP_GH_WEBHOOK_SECRET
    pidfile: .the-loop/gh-webhook.pid
    events: []
    routing: {}     # see /config/cli/routing-options
```

Every option here is also a flag on `gh-webhook start`, and **the flag always wins**.

## Listener

### `host`

- **Type:** `string`
- **Default:** `127.0.0.1`

Interface/IP the receiver binds. Keep the loopback default unless something in front of it
— a reverse proxy, a tunnel, a VPN — is providing the exposure and the TLS. The receiver
speaks plain HTTP and authenticates callers only by HMAC (see `secretEnv`), so binding it
to `0.0.0.0` on a public host puts an unencrypted endpoint on the internet.

### `port`

- **Type:** `integer` (1–65535)
- **Default:** `8787`

Listen port.

### `path`

- **Type:** `string`
- **Default:** `/gh-webhook`

HTTP path the receiver serves. Point your GitHub webhook at
`http(s)://<host>:<port><path>`. `GET /health` is served unconditionally and returns
`200 ok` — use it for a readiness probe.

### `pidfile`

- **Type:** `string`
- **Default:** `<state.root>/gh-webhook.pid` (i.e. `.the-loop/gh-webhook.pid`)

Written on `start`, read on `stop`. Set it explicitly and the value is used verbatim;
leave it out and it derives from [`state.root`](/config/cli/#state-root).

## Verification

### `secretEnv`

- **Type:** `string`
- **Default:** `THE_LOOP_GH_WEBHOOK_SECRET`

Name of the **environment variable** holding the GitHub webhook secret used to verify the
`X-Hub-Signature-256` HMAC on every delivery.

::: danger This is a variable name, never the secret
The secret is read from the environment and never from this file and never from a flag, so
it cannot leak into a committed config or a process listing:

```bash
export THE_LOOP_GH_WEBHOOK_SECRET='…'   # the same value you gave GitHub
the-loop gh-webhook start
```

If the variable is unset, HMAC verification is not performed — anyone who can reach the
port can post an event. Set it.
:::

## Event filter

### `events`

- **Type:** `string[]`
- **Default:** `[issues, issue_comment, pull_request, pull_request_review, pull_request_review_comment, workflow_run, check_run, check_suite, status]`

GitHub event names the receiver cares about. Omitted or empty means the default set above
— every event the-loop can map to a work item, so nothing routable is missed. An explicit
list narrows it.

::: warning Keep `issues` and `pull_request`
Without them a closed issue or a merged PR never arrives, so its session — and its tmux
session with it — is never closed, and finished work items accumulate as live agents. The
receiver warns at startup when either is missing.
:::

## Next

- [Routing options](/config/cli/routing-options) — what the receiver *does* with an
  accepted event.
- [`the-loop gh-webhook`](/cli/commands/gh-webhook) — the command, its flags and its
  guards.
