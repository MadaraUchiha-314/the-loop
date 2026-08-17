# Observability options

Three top-level blocks that answer "what happened, and who hears about it":
`eventLog` (the trail the daemon writes), `collaborators` (who the operator is) and
`notifications` (which daemon events reach them).

```yaml
eventLog:
  enabled: true
  path: .the-loop/logs/events.jsonl

collaborators:
  - handle: "@octocat"
    roles: [engineer, approver]

notifications:
  enabled: true
  events:
    dispatch-failed: [engineer]
    event-dropped-unauthorized: [approver]
```

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

## Operator collaborators

### `collaborators`

- **Type:** `object[]`
- **Default:** `[]`
- **Related:** [decision-035](/decisions/decision-035)

The **operator's own** notification recipients — typically just themself. Same structure as
a repository's `.the-loop/collaborators.yaml` (`handle`, `kind`, `roles`, `notifications`
with per-channel settings — see [collaborators](/config/harness-config#collaborators)), but
**declared here rather than looked up**.

::: warning Declared, not discovered
The daemon never reads any repository's `collaborators.yaml`. It watches many repos and
belongs to none of them, so the people it may ping are a property of the operator, not of
whichever repo raised the event.
:::

`roles` is what the [notifications](#notifications) events target.

## Notifications

Which **daemon-side** events notify which roles from `collaborators` above.

These are disjoint from the harness-side taxonomy in
[`harness-config.yaml`](/config/harness-config) — decision pending, PR review pending, and
so on. Those are raised by the harness *inside* a repository checkout; these concern the
daemon itself. An event with no roles listed notifies nobody.

### `notifications.enabled`

- **Type:** `boolean`
- **Default:** `true`

Master switch for daemon-raised notifications.

### `notifications.events.work-item-spawned`

- **Type:** `string[]` (roles)
- **Default:** none — nobody notified

A session was spawned for a work item (auto-execute label, or `spawnOnUnmatched: always`).

### `notifications.events.dispatch-failed`

- **Type:** `string[]` (roles)
- **Default:** none — nobody notified

A harness dispatch failed **terminally**: `poll.spawn_failed` / `poll.comment_failed` after
[`polling.maxRetries`](/config/cli/polling-options#maxretries), or a webhook dispatch
error. This is the one most operators want on — it is the difference between "the-loop is
quiet because there is nothing to do" and "the-loop is quiet because it is broken".

Independently of this setting, an abandoned **comment** is also reported on the work item
itself (`poll.giveup_reported`, issue-240), so the person who wrote it learns it never
reached the session even if nobody wired this notification up.

### `notifications.events.session-died`

- **Type:** `string[]` (roles)
- **Default:** none — nobody notified

A registered tmux session was found dead, and respawned where possible.

### `notifications.events.event-dropped-unauthorized`

- **Type:** `string[]` (roles)
- **Default:** none — nobody notified

An event was dropped by the authorized-actor guard
([`routing.authorizedUsers`](/config/cli/routing-options#authorizedusers)). Worth routing
somewhere: a steady trickle is normal (other people commenting on your tickets), but a
sudden burst is either a misconfigured `authorizedUsers` or somebody probing.

::: tip How a notification is actually delivered
Through the [channels](/config/cli/channels-options) layer — the Slack bot posts every
event a channel's `events` allow-list subscribes to, with the token taken from an
environment variable, never from this file. (The old `integrations.slack` incoming
webhook converged into channels — issue-245; `the-loop migrate-config` retires it.)
:::

## Next

- [`the-loop events`](/cli/commands/events) — querying the trail.
- [Channels options](/config/cli/channels-options) — the surface notifications go
  out over, and replies come back in on.
