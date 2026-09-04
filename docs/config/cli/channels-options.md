---
configBase: channels
---

# Channels options

Options under `channels` — the surfaces the-loop talks on
([issue-245](https://github.com/MadaraUchiha-314/the-loop/issues/245),
[issue-309](https://github.com/MadaraUchiha-314/the-loop/issues/309)).

Every channel is a **peer on one event bus** ([decision-103](/decisions/decision-103)):
it **subscribes** to the event types it wants to receive, it may **publish** the event
types a message on it is granted to become, and it renders every event itself. One
channel is the **ledger** — the channel of record every event is written to before any
other channel sees it — GitHub, by default and for now. Distinct from
[`integrations`](/config/cli/integrations-options), deliberately: an integration is a
transport for the-loop's own one-shot calls; a channel is a conversation.

```yaml
routing:
  authorizedUsers:                          # identity, declared once — see routing options
    - github: octocat
      slack: U0456GHIJKL
channels:
  ledger: github
  slack:
    enabled: true
    botTokenEnv: THE_LOOP_SLACK_BOT_TOKEN   # xoxb-, chat:write + channels.history
    appTokenEnv: THE_LOOP_SLACK_APP_TOKEN   # xapp-, only for read.mode: socket
    channel: C0123ABCDEF                     # the channel the bot posts into
    subscribe: [session.awaiting_input, phase-approval-pending, comment.agent]
    publish: [work-item.reply, gate.feedback]
    verbosity: normal
    maxChars: 1500
    kickoff:
      repo: octocat/hello-world
      labels: ["the-loop: auto-execute"]
    read:
      mode: socket                           # poll | socket | off
      intervalSeconds: 30
```

An asked question ([`the-loop ask`](/cli/commands/ask)) is recorded on the ledger first
— the record *is* the question comment — then reaches every channel subscribed to
`session.awaiting_input`; a thread reply from an authorized member becomes whatever
the channel's `publish` list grants: session input by default, a gate answer or a
control keyword or a new work item by grant — each recorded on the ledger and **judged
by the ledger's own ingress**, never around it. Operate it with
[`the-loop channels`](/cli/commands/channels).

**One thread per work item, the thread is the work item's, and it opens when the work
item starts** ([issue-312](https://github.com/MadaraUchiha-314/the-loop/issues/312),
[decision-105](/decisions/decision-105);
[issue-317](https://github.com/MadaraUchiha-314/the-loop/issues/317),
[decision-107](/decisions/decision-107)). The moment a start is accepted the dispatcher
opens a root message that names the work item (the ref, with an *Open on GitHub* button)
— before the checkout, on every enabled channel — and every event is a **reply** into
it. A channel that is down at start time costs nothing but a `channel.open_failed` line:
the first event then opens the root lazily. The root is opened once, under a lock on the
channel's state, whichever of the-loop's processes gets there first; a thread a member
started that became a work item (`work-item.create`) is that work item's thread.
[`the-loop channels threads`](/cli/commands/channels) lists which thread carries which
work item, and how it was opened.

## The ledger

### `ledger`

- **Type:** `'github'`
- **Default:** `github`

The channel of record. Every event that originates elsewhere is written here before
any other channel receives it — as a comment carrying a machine-readable **envelope**
naming the event type, the source channel and the person, or as the issue itself for
`work-item.create`. The ledger's ingress (the webhook receiver and the poller) is what
acts on a relayed gate answer or control keyword, through the same guards a typed
comment goes through. GitHub is the only value this release ships; the key is the
extension point the owner named. An unknown value is refused at load.

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
and `channels:history` to read). The config names the *variable*, the token is read from
the environment **at call time**, and the value never appears in config, state files,
`channels status` output or the event log.
The variable can be set in the shell or in a `.env` file the config names
([`env.file`](/config/cli/#env-file)), loaded when each process starts.

### `slack.appTokenEnv`

- **Type:** `string`
- **Default:** `THE_LOOP_SLACK_APP_TOKEN`

The environment variable holding the app-level token (`xapp-…`, scope
`connections:write`) that [`the-loop channels listen`](/cli/commands/channels) needs
for Socket Mode — the no-polling read transport, and the only one that can receive a
button press. Unused in `poll` mode.

### `slack.channel`

- **Type:** `string`
- **Default:** `""`

The id of the Slack channel the bot posts into (`C…` — copy it from the channel's
details pane; ids, unlike names, survive renames). The bot must be a member. Empty
disables posting, with a recorded reason per attempt.

### `slack.subscribe`

- **Type:** `string[]`
- **Default:** `["session.awaiting_input"]`

The event types this channel **receives**. Was `events` before issue-309 —
[`the-loop migrate-config`](/cli/commands/migrate-config) renames it. The names come
from **one catalog** (printed with subscription ticks by
[`the-loop channels status`](/cli/commands/channels)):

| Event | Fires when |
|-------|-----------|
| `session.awaiting_input` | an agent asked a human a question (`the-loop ask`) and is waiting — the default subscription |
| `decision-pending` | the graph reached a point where a human decision or opinion is genuinely required |
| `phase-approval-pending` | a spec-chain phase (requirements, design + testing plan) is ready for its human gate — the message carries a link and an excerpt of the artifact |
| `pr-review-pending` | a pull request delivering the work item is ready for human review |
| `security-sign-off-pending` | the work item's risk tier requires a named human security sign-off |
| `conflict-escalated` | the loop hit a genuine block, logged the conflict and escalated once |
| `work-item-complete` | the work item reached `complete` (fired since issue-309 — a channel that had subscribed starts receiving it) |
| `comment.agent` | the agent's own comment landed on the work item (marker-stamped): the requirements summary, the phase checklist, a review note |
| `comment.human` | a human comment the ledger accepted — an authorized user's or a work-item collaborator's. A stranger's comment is relayed nowhere |
| `standing.started` | a [standing session](/capabilities/standing-sessions) came up and opened its thread |

A name outside the catalog is **kept but warned about** (a custom process graph may
fire a custom `notify` event; a typo would otherwise fail silently). A test pins the
catalog to this table and to the harness config's notification taxonomy.

Subscribe to `comment.agent` alone and the bound thread carries what the agent wrote
and no human's words; add `comment.human` and it carries the thread. A record the bus
itself made — a reply's mirror, a relayed gate answer, the ask — is never re-published
as a comment event: the channel that raised it already has it.

### `slack.publish`

- **Type:** `string[]`
- **Default:** `["work-item.reply"]`

What a message on this channel **may become** — the channel's authority, per event type
([decision-103 D2](/decisions/decision-103)). A message is classified into exactly one
type, in a fixed order, and a type not listed here is **dropped, never downgraded**
(recorded as `channel.dropped` with `reason: unpublishable-event`): a control keyword
typed on a channel without the grant does not reach the agent as prose either.

| Grant | A message becomes it when | What happens |
|-------|---------------------------|--------------|
| `work-item.reply` | none of the below applies | mirrored onto the work item as the-loop's own marked comment (quoted, scrubbed, keywords defanged) and **delivered into the waiting session** — 12.1.0's behaviour, the default |
| `gate.feedback` | the work item's graph is parked at a human gate | recorded on the ledger as an **unmarked** comment under your own credential, with the envelope and a visible "answer from `slack:U…`" attribution; the ledger's ingress then classifies it exactly as a typed approval, and the artifact's `approvedBy` names the person the envelope names |
| `control.command` | the text carries a [control keyword](/config/cli/routing-options#execution-control) | recorded the same way, keyword intact; the ledger's ingress executes it through the same named-actor control seam |
| `work-item.create` | the message is **top-level** in the configured channel | an issue is created in `kickoff.repo` with `kickoff.labels` — needs both the grant and the repo |

The ordering (keyword → gate → reply) means an approval word inside a control comment
never becomes a gate answer, and "not at a gate" — no session, no graph coupling — is
the fail-closed direction: the message is a reply. A relayed gate answer or control
keyword moves the loop on the ledger's **next ingress**: a webhook delivery, or one poll
interval. A name the catalog does not mark publishable is ignored with a warning — a
typo can never widen what a chat message may do.

### `slack.verbosity`

- **Type:** `'quiet' | 'normal' | 'verbose'`
- **Default:** `normal`

How much of an event each message carries: `quiet` is the header plus the link button;
`normal` adds the text (and, for an approval, the artifact excerpt); `verbose` adds
the context detail. Strict supersets — turning it down never changes the words, only
how many of them there are.

### `slack.maxChars`

- **Type:** `integer` (minimum 200)
- **Default:** `1500`

The cap on the text one Slack message carries — a comment body, an artifact excerpt.
Longer text is cut with a note, and the link button points at the rest.

### `slack.kickoff.repo`

- **Type:** `string`
- **Default:** `""`

The `[host/]owner/repo` a top-level message becomes an issue in, when the channel holds
the `work-item.create` grant — `gh`'s own `--repo` grammar, so a GitHub Enterprise
deployment names its host and the bound ref carries it (issue-311). Both are needed: there is no sensible inferred answer to
"which repository does this DM become an issue in", so an empty `repo` disables the
path whatever `publish` says. The first read after the grant is turned on
**baselines** the channel: nothing already there becomes an issue. The created
issue's body carries the envelope and no self-authored marker (it must be armable);
the thread is bound to the new work item and told the link.

### `slack.kickoff.labels`

- **Type:** `string[]`
- **Default:** `[]`

Labels applied to the created issue — **from here and only here**, never from the
message. Add [`routing.autoExecuteLabel`](/config/cli/routing-options#autoexecutelabel)
to arm the item for `the-loop start`, or leave it empty to file the issue and stop.

### `slack.read.mode`

- **Type:** `'poll' | 'socket' | 'off'`
- **Default:** `poll`

How messages come back. `poll`: the long-running daemons fetch new thread replies (and,
with the kickoff grant, new top-level messages) on a background thread, and
`the-loop channels poll` runs one cycle for cron or daemon-less deployments. `socket`:
`the-loop channels listen` receives them push-fashion over Socket Mode — no polling, no
inbound HTTP endpoint — and it is the only mode that receives a **button press**, so
Approve / Request changes buttons are rendered only here (and only with the
`gate.feedback` grant): a button nobody can receive is worse than none. `off`: nothing
is read. An unknown value resolves to `off` with a warning — never to a reading mode by
accident.

### `slack.read.intervalSeconds`

- **Type:** `integer` (minimum 5)
- **Default:** `30`

Poll-mode cadence. A cycle with no bound threads and no kickoff grant makes no API call
at all.

## Who may speak

`channels.slack.authorizedUsers` is gone (issue-309). The Slack member ids the channel
acts on are the `slack` ids of the person entries under
[`routing.authorizedUsers`](/config/cli/routing-options#authorizedusers) — identity is
declared once, with each person's id on every channel, and read per channel. Empty
denies every reply, button press and kickoff (fail closed).
