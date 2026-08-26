# Observability options

One top-level block that answers "what happened": `eventLog`, the trail the daemon writes.

```yaml
eventLog:
  enabled: true
  path: .the-loop/logs/events.jsonl
```

Who *hears* about it is a different question, answered on a different page —
[channels options](/config/cli/channels-options). The CLI config used to carry an
operator `collaborators` list and a daemon-side `notifications.events` filter beside the
event log; both were removed in issue-304 because **no code read either of them**. See
[what replaced them](#where-the-notifications-went).

## Event log

Every routing, dispatch and session decision the CLI makes — by the receiver, the poller
**and** the `sessions` command — is appended as one JSON object per line. It is the
end-to-end observability trail, queried with [`the-loop events`](/cli/commands/events).

The file is plain JSONL, so `grep`, `jq` and `tail -f` work directly on it. Writes are
append-only and multi-process safe, and a broken log never breaks ingress.

Record schema and agent guidance:
[observability reference](/operating-model/reference/observability). Why JSONL and not
SQLite: [decision-025](/decisions/decision-025).

### `eventLog.enabled`

- **Type:** `boolean`
- **Default:** `true`

Emit the event log. `false` turns emission off entirely.

### `eventLog.path`

- **Type:** `string`
- **Default:** `<state.root>/logs/events.jsonl`

Append-only JSONL file; git-ignored runtime state. Unset, it resolves under
[`state.root`](/config/cli/#state-root) — `.the-loop/logs/events.jsonl` with the default
root.

## Where the notifications went

Until issue-304 this page also documented two blocks that looked like notification config
and were not:

| Removed | What it claimed | What actually happened |
|---------|-----------------|------------------------|
| `collaborators` | the operator's own recipients, resolved by role | nothing read the list |
| `notifications.events` | four daemon events → roles (`work-item-spawned`, `dispatch-failed`, `session-died`, `event-dropped-unauthorized`) | those event names are raised by no code; the filter was never consulted |

An operator who filled them in configured nothing, and nothing said so. They are gone, and
[`the-loop migrate-config`](/cli/commands/migrate-config) strips them from an existing
config and bumps its version — a config still carrying either is **refused** at load,
naming the key and the fix, rather than loaded half-configured.

What to use instead:

- **To be notified:** [`channels.slack`](/config/cli/channels-options). One bot for the
  whole daemon — `botTokenEnv`, a `channel` id, and an `events` allow-list you subscribe to
  the event names you care about. It carries replies back, too.
- **To say who may drive the daemon:**
  [`routing.authorizedUsers`](/config/cli/routing-options#authorizedusers) (GitHub logins).
- **To say whose Slack reply is acted on:**
  [`channels.slack.authorizedUsers`](/config/cli/channels-options) (Slack member ids).

Those two lists are the only places human identity is declared. Per-person notification
routing is **not built**: a notification goes to a channel, not to a person.

::: tip The harness side is unaffected
`harness-config.yaml`'s own [`notifications.events`](/config/harness-config) is a different
taxonomy — `decision-pending`, `phase-approval-pending`, and friends — and it is still
read: it gates the process graph's `notify` hook, which then posts through the channels
layer.
:::

## Next

- [`the-loop events`](/cli/commands/events) — querying the trail.
- [Channels options](/config/cli/channels-options) — the surface notifications go
  out over, and replies come back in on.
