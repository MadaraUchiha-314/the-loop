---
configBase: channels
---

# Channels options

Options under `channels` — the surfaces the-loop holds a **back-and-forth
conversation** on ([issue-245](https://github.com/MadaraUchiha-314/the-loop/issues/245)).

Distinct from [`integrations`](/config/cli/integrations-options), deliberately: an
integration is a transport for the-loop's own one-shot calls; a **channel** also reads,
filters the event types it wants, renders at a configured verbosity, and mirrors every
reply onto the work item — the single source of truth — as the-loop's own
marker-stamped comment, so nothing is processed twice. This is **the** Slack surface:
the graph's `notify` hook posts its notification events through the same filter, and
the old `integrations.slack` incoming webhook is retired (issue-245, PR #267 review —
[`the-loop migrate-config`](/cli/commands/migrate-config) removes an old section).

```yaml
channels:
  slack:
    enabled: true
    botTokenEnv: THE_LOOP_SLACK_BOT_TOKEN   # xoxb-, chat:write + channels.history
    appTokenEnv: THE_LOOP_SLACK_APP_TOKEN   # xapp-, only for read.mode: socket
    channel: C0123ABCDEF                     # the channel the bot posts into
    events: [session.awaiting_input]
    verbosity: normal
    authorizedUsers: [U0456GHIJKL]           # Slack MEMBER ids — empty denies all
    read:
      mode: poll                             # poll | socket | off
      intervalSeconds: 30
```

An asked question ([`the-loop ask`](/cli/commands/ask)) lands on the work item first,
then fans out to every enabled channel subscribed to `session.awaiting_input`; a thread
reply from an authorized member is mirrored onto the ticket and delivered into the
waiting session. Operate it with [`the-loop channels`](/cli/commands/channels).

## Slack

### `slack.enabled`

- **Type:** `boolean`
- **Default:** `false`

Default off: enabling the daemons never becomes consent to posting into (or reading
from) a Slack workspace. A malformed section also resolves to disabled, loudly — fail
closed, never half-enabled.

### `slack.botTokenEnv`

- **Type:** `string`
- **Default:** `THE_LOOP_SLACK_BOT_TOKEN`

The environment variable holding the bot token (`xoxb-…`, needing `chat:write` to post
and `channels:history` to read thread replies). The same arrangement as
[`webhooks.ghWebhook.secretEnv`](/config/cli/webhook-options#secretenv): the config
names the *variable*, the token is read from the environment **at call time**, and the
value never appears in config, state files, `channels status` output or the event log.

### `slack.appTokenEnv`

- **Type:** `string`
- **Default:** `THE_LOOP_SLACK_APP_TOKEN`

The environment variable holding the app-level token (`xapp-…`, scope
`connections:write`) that [`the-loop channels listen`](/cli/commands/channels) needs
for Socket Mode — the no-polling read transport. Unused in `poll` mode.

### `slack.channel`

- **Type:** `string`
- **Default:** `""`

The id of the Slack channel the bot posts into (`C…` — copy it from the channel's
details pane; ids, unlike names, survive renames). The bot must be a member. Empty
disables posting, with a recorded reason per attempt.

### `slack.events`

- **Type:** `string[]`
- **Default:** `["session.awaiting_input"]`

The event-type allow-list: only these are posted to this channel. The names come from
**one common catalog** (`SUBSCRIBABLE_EVENTS`, printed with subscription ticks by
[`the-loop channels status`](/cli/commands/channels)) — the ask plus everything the
graph's `notify` hook can fire. Which *roles* each notification event pings stays in
the harness config's `notifications.events`; this list decides which events reach
*this channel*.

| Event | Fires when |
|-------|-----------|
| `session.awaiting_input` | an agent asked a human a question (`the-loop ask`) and is waiting — the default subscription |
| `decision-pending` | the graph reached a point where a human decision or opinion is genuinely required |
| `phase-approval-pending` | a spec-chain phase (requirements, design + testing plan, tasks) is ready for its human gate |
| `pr-review-pending` | a pull request delivering the work item is ready for human review |
| `security-sign-off-pending` | the work item's risk tier requires a named human security sign-off |
| `conflict-escalated` | the loop hit a genuine block, logged the conflict and escalated once |
| `work-item-complete` | the work item reached `complete` |

A name outside the catalog is **kept but warned about** (a custom process graph may
fire a custom `notify` event; a typo would otherwise fail silently — the event would
just never arrive). A test pins the catalog to the harness config's notification
taxonomy and to this table, so none of the three can drift.

### `slack.verbosity`

- **Type:** `'quiet' | 'normal' | 'verbose'`
- **Default:** `normal`

How much of an event each message carries: `quiet` is one line plus the work-item
link; `normal` adds the full question text; `verbose` adds context detail (actor,
comment URL). Strict supersets — turning it down never changes the words, only how
many of them there are.

### `slack.authorizedUsers`

- **Type:** `string[]`
- **Default:** `[]`

The Slack **member ids** (`U…` — ids, not display names, which are attacker-chosen)
whose thread replies the-loop acts on. The
[`routing.authorizedUsers`](/config/cli/routing-options#authorizedusers) posture
exactly: an empty list denies every reply (fail closed), and an unauthorized reply is
neither delivered into the session nor mirrored onto the ticket.

### `slack.read.mode`

- **Type:** `'poll' | 'socket' | 'off'`
- **Default:** `poll`

How replies come back. `poll`: the long-running daemons fetch new thread replies on a
background thread, and `the-loop channels poll` runs one cycle for cron or daemon-less
deployments. `socket`: `the-loop channels listen` receives them push-fashion over
Socket Mode — no polling, and no inbound HTTP endpoint to expose. `off`: nothing is
read. An unknown value resolves to `off` with a warning — never to a reading mode by
accident. Both transports read **only** threads the-loop itself started.

### `slack.read.intervalSeconds`

- **Type:** `integer` (minimum 5)
- **Default:** `30`

Poll-mode cadence. A cycle with no bound threads makes no API call at all; with
bindings it is one `conversations.replies` call per open thread.
