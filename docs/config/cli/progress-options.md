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
