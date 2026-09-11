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
    maxChars: 1500                           # and the threshold for longMessages
    longMessages: digest                     # digest | truncate — above maxChars
    kickoff:
      repo: octocat/hello-world
      labels: ["the-loop: auto-execute"]
    read:
      mode: socket                           # poll | socket | off
      intervalSeconds: 30
    reactions:                               # acknowledge an accepted message on itself
      enabled: true
      received: eyes                         # 👀 the moment it is accepted
      completed: white_check_mark            # ✅ when the action landed
      error: warning                         # ⚠️ when it did not
```

The operator's map of every way to drive the loop from Slack — setup, the thread, the
buttons, the kickoff, the `/the-loop` slash command, standing sessions, the control
plane — is the [Slack integration guide](/guide/slack).

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

The environment variable holding the bot token (`xoxb-…`, needing `chat:write` to post,
`channels:history` to read — `groups:history` in a private channel — `reactions:write` to
[acknowledge](/config/cli/channels-options#slack-reactions-enabled) a reply on the reply
itself, and `commands` for the [slash command](#the-slash-command); the packaged
[app manifest](/guide/slack#_1-create-the-slack-app-from-the-manifest) declares them all). The config names
the *variable*, the token is read from the environment **at call time**, and the value
never appears in config, state files, `channels status` output or the event log.
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
| `gate.feedback` | the work item's graph is parked at a human gate — or the pipeline **cannot tell** (no session record, no checkout, a read fault) | recorded on the ledger as an **unmarked** comment under your own credential, with the envelope and a visible "answer from `slack:U…`" attribution (a "reply from" when the gate could not be read); the ledger's ingress then classifies it exactly as a typed approval — with the graph it actually keeps — and the artifact's `approvedBy` names the person the envelope names |
| `control.command` | the text carries a [control keyword](/config/cli/routing-options#execution-control) — typed, or pressed as the **Execute** / **Start** button ([issue-337](https://github.com/MadaraUchiha-314/the-loop/issues/337)) | recorded the same way, keyword intact; the ledger's ingress executes it through the same named-actor control seam. With `read.mode: socket` this grant also renders the Execute button on the phase-selection checklist and the Start button on a kickoff's reply, each carrying the configured keyword as its value |
| `work-item.create` | the message is **top-level** in the configured channel | an issue is created in `kickoff.repo` with `kickoff.labels` — needs both the grant and the repo |
| `instance.command` | a `/the-loop status`, `restart` or `upgrade` [slash command](#the-slash-command) | the core facade `the-loop status` / `the-loop restart [--with-upgrade]` run — answered ephemerally; **not recorded** (no ticket), the event log is the trail ([issue-334](https://github.com/MadaraUchiha-314/the-loop/issues/334)) |
| `standing.command` | a `/the-loop standing list\|start\|stop\|restart <name>` slash command | the same core verb `the-loop standing <verb>` runs; not recorded |

A `/the-loop <keyword> <work-item>` slash command is `control.command` too — the same
unmarked record on the ticket, the same execution by the ledger's ingress — so one grant
covers a keyword typed in the thread and a keyword sent as a command. The ordering
(keyword → gate → reply) means an approval word inside a control comment
never becomes a gate answer. The gate is read through the dispatcher's own coupling —
the same control policy, control store and registry the ingress reads with (issue-321,
[decision-109](/decisions/decision-109)) — and the read has three answers. *At a gate*
is a gate answer. *Not at a gate*, or `routing.graph.enabled: false`, is a reply with
direct delivery. *Cannot tell* — no session record, a record with no checkout, a read
fault — defers to the reader that can: with this grant the reply is recorded unmarked
and the ledger's ingress judges it; without it the reply is the marked mirror it always
was, so a channel that may not answer gates still never does. The event log says which
(`channel.reply_received`, `gate: open | none | unknown`). A relayed gate answer or
control keyword moves the loop on the ledger's **next ingress**: a webhook delivery, or
one poll interval. A name the catalog does not mark publishable is ignored with a
warning — a typo can never widen what a chat message may do.

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

How much text one Slack message carries — a comment body, an artifact excerpt — and
the threshold above which `longMessages` (below) applies
([issue-338](https://github.com/MadaraUchiha-314/the-loop/issues/338)). At most
Slack's own 3000-character section limit. This is the lever for a small screen: a
phone reader turns it *down*, and the digest fits the message to it.

### `slack.longMessages`

- **Type:** `'digest' | 'truncate'`
- **Default:** `digest`

What happens to a text section longer than `maxChars`
([issue-338](https://github.com/MadaraUchiha-314/the-loop/issues/338),
[decision-118](/decisions/decision-118)).

`digest` — a **structural** digest the channel computes, with no model involved: the
first question in the text (or, failing one, the sentence that says *reply `…`*) goes
first, in bold; a list becomes numbered lines (`1.`, `2.`, … — GitHub task boxes drawn
as ☑ / ☐); every code fence, markdown table and stack trace is replaced in place by a
pointer (*⟨code: 12 lines⟩*, *⟨table: 4 rows⟩*, *⟨stack trace: 9 lines⟩*); an absolute
path of three or more segments loses its head (`…/channels/slack.py`); the rest follows
in the author's order until the budget is spent; the cut falls on a sentence (a clause,
or a word, only when no sentence fits); and one closing line links the full text —
*… full text: GitHub* — whenever anything was cut, left out or replaced. Every sentence
in a digest is one the author wrote: the digest reorders, numbers and points; it never
paraphrases.

`truncate` — the first `maxChars` characters and a *… (N more characters — see the
link)* note — 13.10.0's behaviour.

A text at or under `maxChars` is posted **whole** either way, in the author's order,
with no pointer and no closing line. Whatever the length, GitHub markdown is drawn as
Slack mrkdwn (`**bold**` → `*bold*`, headings, links, task boxes, bullets) and an HTML
comment — the-loop's own markers included — is removed: that changes how the words are
drawn, never which words are there. The [Slack guide](/guide/slack#reading-it-on-a-phone)
shows a checklist before and after.

### `slack.kickoff.repo`

- **Type:** `string`
- **Default:** `""`

The `[host/]owner/repo` a top-level message becomes an issue in **when the message does
not name one** — `gh`'s own `--repo` grammar, so a GitHub Enterprise deployment names
its host and the bound ref carries it (issue-311).

Since [issue-341](https://github.com/MadaraUchiha-314/the-loop/issues/341) this is the
**fallback, not the requirement**. A kickoff message may start with a repository prefix:

```
slim-gym: flaky teardown in the batch runner
```

The prefix is resolved against the repositories **you** declared — this `repo` plus
every `repos` entry of every `github` source in
[`polling.sources`](/config/cli/polling-options) — as a bare repository name, an
`owner/repo`, or a `host/owner/repo`; the prefix is stripped before the issue is
composed, and `kickoff.labels` applies whichever repository is chosen. Nothing is
inferred beyond that list ([decision-120](/decisions/decision-120)):

| The first line | What happens |
|----------------|--------------|
| a prefix naming exactly one declared repository | the issue is opened there |
| `owner/repo:` naming none, or a bare name matching several | **refused** — ⚠️ on your message and a reply naming the candidates; nothing is created |
| a bare word matching none (`fix: …`) | not treated as a prefix; the message goes to this `repo` unchanged |
| no prefix, this `repo` empty | refused, with a reply asking for a `<repo>:` prefix |

So `work-item.create` with an empty `repo` is now a **valid** configuration —
prefix-only kickoff — rather than a dead one. Every refusal reaches only a member on
`routing.authorizedUsers`: an unlisted member is still dropped in silence and told
nothing, including which repositories exist.

The first read after the grant is turned on **baselines** the channel: nothing already
there becomes an issue. The created issue's body carries the envelope and no
self-authored marker (it must be armable); the thread is bound to the new work item and
told the link.

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
inbound HTTP endpoint — running one **catch-up read** over the bound threads the moment
it connects (issue-334), so what was posted while no listener was connected is processed
once from the shared cursors (`the-loop channels poll` runs the same cycle on demand in
this mode too, as a reconciliation); and it is the only mode that receives a **button press**, so
Approve / Request changes buttons are rendered only here (and only with the
`gate.feedback` grant), and so are the **Execute** / **Start** buttons (only with the
`control.command` grant — [issue-337](https://github.com/MadaraUchiha-314/the-loop/issues/337)):
a button nobody can receive is worse than none — and it is the only mode the
[`/the-loop` slash command](#the-slash-command) can arrive in. A processed press is
written back onto the pressed message (the buttons replaced by the outcome line);
`the-loop channels status` prints the steps a configuration still needs before a press
can arrive. See the [Slack guide's buttons section](/guide/slack#the-buttons). `off`: nothing
is read. An unknown value resolves to `off` with a warning — never to a reading mode by
accident.

### `slack.read.intervalSeconds`

- **Type:** `integer` (minimum 5)
- **Default:** `30`

Poll-mode cadence. A cycle with no bound threads and no kickoff grant makes no API call
at all.

## The slash command

`/the-loop` ([issue-334](https://github.com/MadaraUchiha-314/the-loop/issues/334),
[decision-116](/decisions/decision-116)) is the channel's third inbound shape — the one
for things that have **no thread to type into**: a work item that has not started, a
standing session that is not running, this instance itself. It arrives over **Socket
Mode only** (`read.mode: socket`; Slack needs an acknowledgment within seconds, which a
poll cycle cannot give), is judged by the same `slack` ids of
[`routing.authorizedUsers`](/config/cli/routing-options#authorizedusers) — an unlisted
member gets no answer — and each verb family needs its grant in `publish`:

| Verbs | Grant | Where it goes |
|-------|-------|---------------|
| `<keyword> <work-item> [@login] [instance:<name>]` — `start`, `stop`, `pause`, `resume`, `execute`, `contribute`, `do`, `review`, `cleanup`, `add-collaborator`, `remove-collaborator` | `control.command` | the ledger, as an unmarked comment composed from the configured keyword; the ingress executes it. The work item (`#N` against `kickoff.repo`, `owner/repo#N`, `github:…`, a URL) must be in a repository this instance is configured for (`kickoff.repo`, `polling.sources`) or one it already manages |
| `status` · `restart` · `upgrade` | `instance.command` | `core.lifecycle` — what `the-loop status` and `the-loop restart [--with-upgrade]` run |
| `standing list` · `standing start\|stop\|restart <name>` | `standing.command` | `core.standing` — what `the-loop standing <verb>` runs |

The answer is ephemeral, through the command's `response_url` (Slack's own host only).
The app manifest `the-loop channels manifest` prints declares the command; the
[guide](/guide/slack#the-slash-command-in-full) has the full grammar and the limits.
No configuration key is added: the grants and `read.mode` are the switches, and
`the-loop channels status` prints a `commands:` line saying which families this channel
may run, or why none can arrive.

## Acknowledgments

### `slack.reactions.enabled`

- **Type:** `boolean`
- **Default:** `true`

Acknowledge an **accepted** inbound message with a reaction on that message
([issue-325](https://github.com/MadaraUchiha-314/the-loop/issues/325),
[decision-111](/decisions/decision-111)) — the channel-side mirror of the ticket's
[`routing.reactions`](/config/cli/routing-options#reactions-enabled). The moment a
thread reply, a button press or a top-level kickoff message passes authorization,
classification and the `publish` grant — and *before* the ledger record — the bot adds
`received` to it; when the pipeline's action has landed it adds `completed`, or `error`
when it has not. So the operator replying from a phone sees 👀 within a poll interval
(instantly over Socket Mode) and ✅ / ⚠️ when the-loop is done with the message, without
opening GitHub.

*Landed* is defined per event type, and only over what the pipeline itself does: a
`work-item.reply` is complete when it is recorded **and** delivered into the session; a
`gate.feedback` or `control.command` when its unmarked record reached the ledger — the
ledger's ingress acts on it afterwards, and that outcome is not reported here; a
`work-item.create` when the issue exists and the thread is bound to it. A **dropped**
message — a bot's, an unlisted member's, an unpublishable type, an unmapped thread — gets
no reaction: a drop leaves no mark on the channel, as it leaves none on the ticket.

Best-effort by contract: the reaction is posted with the bot token (which needs the
`reactions:write` scope for this and nothing else), a refused reaction is one
`channel.reaction_failed` event and never affects the record or the delivery, and a
missing token makes no call. Reaction-only, no text. Set `false` to opt out; the
channel's own `enabled: false` already means nothing is read, so nothing is acknowledged.

### `slack.reactions.received`

- **Type:** Slack emoji name, or `""`
- **Default:** `eyes` (👀)

Added when the message is accepted, before the record. `""` skips this state.

### `slack.reactions.completed`

- **Type:** Slack emoji name, or `""`
- **Default:** `white_check_mark` (✅)

Added when the pipeline's action landed. `""` skips this state.

### `slack.reactions.error`

- **Type:** Slack emoji name, or `""`
- **Default:** `warning` (⚠️)

Added when the record could not be written, the reply could not be delivered, or the
issue could not be created. `""` skips this state.

Names are Slack emoji names **without colons** — built-in (`eyes`, `+1`, `tada`) or a
workspace's custom emoji — matching `^[a-z0-9_+-]{1,100}$`; surrounding colons are
stripped, and a name outside the grammar is refused at load with a warning and that
state skipped. Slack's palette is open where GitHub's is fixed to eight, which is why
the defaults here can be the ✅ that `routing.reactions` cannot offer.

## Who may speak

`channels.slack.authorizedUsers` is gone (issue-309). The Slack member ids the channel
acts on are the `slack` ids of the person entries under
[`routing.authorizedUsers`](/config/cli/routing-options#authorizedusers) — identity is
declared once, with each person's id on every channel, and read per channel. Empty
denies every reply, button press and kickoff (fail closed).
