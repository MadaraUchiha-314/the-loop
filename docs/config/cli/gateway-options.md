---
configBase: gateway
---

# Gateway options

Options under `gateway` — consume events from a the-loop **gateway** instead of running
ingresses of this instance's own
([issue-496](https://github.com/MadaraUchiha-314/the-loop/issues/496); see
[the capability](/capabilities/gateway) and [the `gateway` command](/cli/commands/gateway)).
The gateway is one process that owns every inbound transport for a fleet — the GitHub
and Jira webhooks, one Slack Socket Mode connection per app, the pollers — stores each
event on its work item's subject before acknowledging the provider, and fans it out on
write to the queue of every instance that consumes that subject. An instance with this
block polls its **own** queue and nothing else.

```yaml
gateway:
  url: http://127.0.0.1:8790
  pollIntervalSeconds: 5
  longPollSeconds: 20
  actors:
    github: [octocat]
    slack: [U0123ABCD]
    jira: []
```

Present, the block switches the instance's hosted ingresses to the **gateway client**
alone: the webhook receiver, the poller and the Slack listener are off whatever
`webhooks`, `polling` and `channels.slack.read` say, and `the-loop status` reads
`off · gateway configured` for the three. The instance's `instance.name` (`default`
when unset) is its queue's identity; a second peer polling under a live name is
refused with `409 duplicate-instance`, so a fleet should name each instance. When the
gateway is unreachable the instance keeps running, retries with back-off and never
falls back to its own ingresses. Absent, the instance behaves exactly as before.

## Options

### `url`

- **Type:** `string`, `http://` or `https://`
- **Default:** none — the one required key; the block is unusable without it

The gateway's base URL. A loopback address (`http://127.0.0.1:8790`, the gateway's
default port) is treated exactly as a remote one — the same client, the same fetch and
commit — so a gateway and an instance share one machine with no special mode. Needs a
restart to change; everything else in the block hot-reloads.

### `pollIntervalSeconds`

- **Type:** `integer`, at least `1`
- **Default:** `5`

Seconds to sleep after an **empty** plain poll. Ignored while `longPollSeconds` is
greater than zero, because a long-poll already waited.

### `longPollSeconds`

- **Type:** `integer`, at least `0`
- **Default:** `20`

How long the gateway may hold an empty fetch open and answer as soon as a delivery is
appended to this queue — sub-second latency with no request between events. `0` is
plain polling: the gateway answers at once and the client sleeps `pollIntervalSeconds`.
The gateway clamps the value to its own `consume.maxWaitSeconds`.

## The actors

Who this instance works for, by provider (`actors`). An event on a subject no claim covers is
routed to the one instance that registered its actor — how the **first** event about a
work item (`the-loop start` by this user) reaches this instance and no other. An actor
already registered by another live instance is refused (`409 duplicate-actor`). The
instance registers these on start and again after every outage.

### `actors.github`

- **Type:** `string[]`, unique
- **Default:** `[]`

GitHub logins.

### `actors.slack`

- **Type:** `string[]`, unique
- **Default:** `[]`

Slack user ids (`U…`).

### `actors.jira`

- **Type:** `string[]`, unique
- **Default:** `[]`

Jira account ids.
