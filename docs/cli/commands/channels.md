# `channels`

Operate the communication [channels](/config/cli/channels-options) — the peers on
the-loop's event bus, starting with the Slack bot
([issue-245](https://github.com/MadaraUchiha-314/the-loop/issues/245),
[issue-309](https://github.com/MadaraUchiha-314/the-loop/issues/309)).

```bash
the-loop channels status    # ledger, subscribe/publish grants, catalog with ticks — no secrets
the-loop channels poll      # one read cycle: bound threads, and top-level messages when granted
the-loop channels listen    # Socket Mode, foreground — replies, button presses, kickoffs
```

## What it does

- **`status`** prints the ledger, the resolved Slack configuration — with token
  **presence** only (`set`/`unset` plus the env var's name), never a value — how many
  people of `routing.authorizedUsers` can speak on it, whether Approve buttons can be
  received, the kickoff target, how many conversations (thread bindings, cursors) the
  channel state holds, and the **catalog**: every subscribable event with a tick where
  `subscribe` names it, and every publishable event with a tick where `publish` grants
  it — so neither list is ever configured by guessing names.
- **`poll`** runs one synchronous read cycle: every bound Slack thread is checked for
  new replies and — with the `work-item.create` grant and a `kickoff.repo` — the
  channel for new top-level messages. Each message is classified into one event type,
  checked against the channel's grants, recorded on the ledger and, for a plain reply,
  delivered into the waiting session. This is the cron-friendly form of what the
  daemons do continuously when [`read.mode`](/config/cli/channels-options#slack-read-mode)
  is `poll`. Exit 1 when the cycle was skipped (channel disabled, wrong read mode,
  missing token), with the reason printed.
- **`listen`** connects over **Socket Mode** (the official SDK's built-in client, an
  *outbound* connection — nothing to expose) and processes messages push-fashion until
  interrupted: thread replies, top-level messages, and Block Kit **button presses**,
  which enter the pipeline as that member's reply carrying the button's text. Needs both
  tokens: the bot token to act, the app-level token (`xapp-…`, `connections:write`) to
  connect.

However a message arrives — a poll cycle here, the daemons' background reader, or the
listener — it goes through the same pipeline: bindings decide relevance, the bot's own
messages are dropped, the member id is checked against the `slack` ids of
[`routing.authorizedUsers`](/config/cli/routing-options#authorizedusers) fail-closed, the
message is classified (control keyword → open gate → reply) and matched against
[`publish`](/config/cli/channels-options#slack-publish), then **recorded on the ledger**
first. A `work-item.reply` is then delivered into the waiting session through the same
fail-closed path `POST /api/v1/sessions/reply` uses — never spawning or resuming
anything; a `gate.feedback` or `control.command` stops at its record, because the
ledger's own ingress is what acts on it; a `work-item.create` is the issue itself.

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| *(action)* | required | One of `status`, `poll`, `listen`. |

## Notes

- Everything is observable as `bus.*` and `channel.*` events —
  [`the-loop events --types`](/cli/commands/events) lists them. Payloads carry ids and
  event types, never message text and never tokens.
- A message is processed **at most once**, across restarts and across the two read
  transports: the per-thread and per-channel cursors are shared state
  (see [state on disk](/cli/state#channel-conversation-state-root-channels-channel-json)).
  A kickoff whose issue creation failed is not retried — a retry could open a second
  issue — so the member posts again if they mean it.
- `poll` and `listen` refuse (exit 1) rather than half-run when the channel is
  disabled or the tokens are missing — the same fail-closed posture as the rest
  of the surface.
