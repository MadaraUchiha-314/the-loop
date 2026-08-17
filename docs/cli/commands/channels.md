# `channels`

Operate the communication [channels](/config/cli/channels-options) — the
back-and-forth surfaces beside the work item, starting with the Slack bot
([issue-245](https://github.com/MadaraUchiha-314/the-loop/issues/245)).

```bash
the-loop channels status    # resolved config + conversation counts, no secrets
the-loop channels poll      # one read cycle over the bound threads
the-loop channels listen    # Socket Mode, foreground — the no-polling reader
```

## What it does

- **`status`** prints the resolved channel configuration — with token
  **presence** only (`set`/`unset` plus the env var's name), never a value —
  and how many conversations (thread bindings, read cursors) the channel state
  holds.
- **`poll`** runs one synchronous read cycle: every bound Slack thread is
  checked for new replies, each authorized reply is mirrored onto its work item
  and delivered into the waiting session. This is the cron-friendly form of
  what the daemons do continuously when
  [`read.mode`](/config/cli/channels-options#slack-read-mode) is `poll` — a
  deployment running neither daemon still has the capability. Exit 1 when the
  cycle was skipped (channel disabled, wrong read mode, missing token), with
  the reason printed.
- **`listen`** connects over **Socket Mode** (the official SDK's built-in
  client, an *outbound* connection — nothing to expose) and processes replies
  push-fashion until interrupted. Needs both tokens: the bot token to act, the
  app-level token (`xapp-…`, `connections:write`) to connect.

However a reply arrives — a poll cycle here, the daemons' background reader, or
the listener — it goes through the same pipeline: bindings decide relevance
(only threads the-loop started), the bot's own messages are dropped, the
[member-id allow-list](/config/cli/channels-options#slack-authorizedusers) is
checked fail-closed, the reply is **mirrored onto the work item** as the-loop's
own marker-stamped comment (the single-source-of-truth rule), and then delivered
into the waiting session through the same fail-closed path
`POST /api/v1/sessions/reply` uses — never spawning or resuming anything.

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| *(action)* | required | One of `status`, `poll`, `listen`. |

## Notes

- Everything is observable as `channel.*` events —
  [`the-loop events --types`](/cli/commands/events) lists them. Payloads carry
  ids, never message text and never tokens.
- A reply is processed **at most once**, across restarts and across the two
  read transports: the per-thread cursor is shared state
  (see [state on disk](/cli/state#channel-conversation-state-root-channels-channel-json)).
- `poll` and `listen` refuse (exit 1) rather than half-run when the channel is
  disabled or the tokens are missing — the same fail-closed posture as the rest
  of the surface.
