---
configBase: progress
---

# Progress options

Options under `progress` — periodic status lines from a long-running session, posted
while the work is happening rather than as one wall of text when it finishes
([issue-340](https://github.com/MadaraUchiha-314/the-loop/issues/340)). The agent
emits them with [`the-loop progress`](/cli/commands/progress); they become a
`session.progress` event.

**Opt-in per work item, by label.** Only a work item that carries
[`label`](#label) emits anything, so adding or removing the label on the ticket starts or
stops the reports on the next one — no config edit, no restart, and no noise on the many
items that do not need it. A channel also has to subscribe to `session.progress`
([`channels.<name>.subscribe`](/config/cli/channels-options)); it is in no default
subscription. With the label absent from a work item, or no channel subscribed,
behaviour is identical to before.

```yaml
progress:
  label: "the-loop: progress"
  minIntervalSeconds: 300
  maxChars: 280
  silenceSeconds: 0
```

## Options

### `label`

- **Type:** `string`
- **Default:** `the-loop: progress`

The label that opts a work item in. Read from the work item's own tracker at the moment
of each report; on Jira, in its Jira-safe form (spaces become hyphens). An empty string
turns the feature off everywhere: the verb reports `disabled` and emits nothing.

### `minIntervalSeconds`

- **Type:** `integer`
- **Default:** `300`

The least time between two reports on one work item. A report sooner than that is
coalesced away — not sent — and the verb says how many seconds remain, so the agent's
next report is the newest one. `0` disables the limit. Measured from the
[event log](/config/cli/observability-options), so it cannot be enforced while
`eventLog.enabled` is `false`.

### `maxChars`

- **Type:** `integer`
- **Default:** `280`

The longest report, in characters, after it is cut to its first two lines. Longer text is
truncated with an ellipsis — this is a signal, and the full detail already goes on the
ticket.

### `silenceSeconds`

- **Type:** `integer`
- **Default:** `0` (off)

The silence watchdog. When an **active** session of a work item carrying
[`label`](#label) has produced no event of any kind for this many seconds, the daemon
emits one `session.silent` event, so a stuck session stops looking like hard work. It is
said **once per silence**: the next needs activity in between.

"Any kind" is any [event-log](/config/cli/observability-options) record naming the work
item, except the watchdog's own and the `bus.*` / `channel.*` bookkeeping every publish
leaves. The label is read only for a session already past the threshold, so a healthy
deployment makes no tracker call. A check runs about every quarter of the threshold
(never faster than 30 seconds or slower than 5 minutes).

It runs inside the poller and the webhook receiver — no new service — and reads the event
log, so it is not started while `eventLog.enabled` is `false`. For the same reason it
reports a stuck **session**, not a dead daemon: a poller that has stopped cannot say so.
Subscribe a channel to `session.silent` to hear it.
