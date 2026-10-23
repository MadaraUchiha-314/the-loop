# `gateway`

Run and inspect the-loop **gateway** — one ingress process for many instances
([issue-496](https://github.com/MadaraUchiha-314/the-loop/issues/496)). The gateway holds
every inbound transport (the GitHub and Jira webhooks, one Slack Socket Mode connection
per app, the pollers), stores each event on its work item's subject before acknowledging
the provider, and fans it out on write to the queue of every instance that consumes
that subject. Instances with a [`gateway` block](/config/cli/gateway-options) poll
their own queue beside their own receiver and poller; only their Slack listener is off.

```bash
the-loop gateway start     [--config PATH] [--format text|json]
the-loop gateway stop      [--config PATH]
the-loop gateway restart   [--config PATH]
the-loop gateway status    [--config PATH] [--format text|json]
the-loop gateway subjects  [--config PATH] [--format text|json]
the-loop gateway instances [--config PATH] [--format text|json]
```

`--config` names the **gateway's** config (`gateway-config.yaml`), not the CLI config:
these verbs read nothing of an instance's. Unset, it resolves like the CLI config does —
`$THE_LOOP_GATEWAY_CONFIG`, then `./.the-loop/gateway-config.yaml`, then
`~/.the-loop/gateway-config.yaml`. The file is validated against the shipped
`gateway-config.schema.json` first; a violation names each offending key and nothing
starts.

## `start`, `stop`, `restart`

`start` spawns `python -m the_loop.gateway.serve --config …` detached, with the pidfile
`<state.root>/gateway.pid` as the lock and `<state.root>/logs/gateway.out` as its log,
and waits for `GET /api/v1/gateway/health` to answer. A second `start` reports
`already running`. `stop` sends `SIGTERM` and waits for the pidfile; `restart` is the
two in order, which is how a change to the start-time-only keys (`listen`, the Slack
tokens) is applied — everything else hot-reloads on the five-second cadence.

A non-loopback `listen.host` without `listen.exposed: true` refuses to start (exit 2):
the instance-to-gateway boundary carries no authentication in this release, so an
exposed gateway is readable, claimable and committable by any peer on that network.

## `status`

```text
gateway: running (pid 842933)
  listen:  127.0.0.1:8790
  store:   ~/.the-loop/gateway/gateway.db
  config:  ~/.the-loop/gateway-config.yaml
  pidfile: ~/.the-loop/gateway/gateway.pid
  log:     ~/.the-loop/gateway/logs/gateway.out
  ingresses: gh-webhook=off, github-poll=running, jira-poll=off, jira-webhook=off, slack-http=off, slack-socket=running
  slack socket: up
  slack posting: on
  instances (lease live): laptop-a
  held on unassigned: 0
  restart required: listen
```

The pid, the enabled ingresses and their state (`running`, `off`, `failed:<reason>` —
`failed:missing-secret` when the variable an ingress needs is unset), the Socket Mode
connection, the store path, the instances that fetched within their lease window, how
many events wait on `unassigned`, and the keys that differ from the running values and
need a restart.

## `subjects`

Every subject with its claimants (instance and role), events, held, pending and dead
counts, and the age of the oldest uncommitted delivery:

```text
subject                                  claimants                                events  held  pending  oldest  dead
loop-github-madarauchiha-314-the-loop-14  laptop-a (driver), laptop-b (reviewer)  12      0     2        8s ago  0
unassigned                               -                                        1       1     0        -       0
```

A subject on `unassigned` is held: no claim and no actor registration matched when the
event arrived; a later claim, binding or registration routes it.

## `instances`

Every instance that fetched, with its lease (`live` while the name is held by its
peer; a second peer under a live name is refused with `409 duplicate-instance`), last
fetch, backlog, committed offset, the actors it registered and the claims it holds.

`--format json` prints the documents `GET /api/v1/gateway/subjects|instances` serve.
See [the gateway capability](/capabilities/gateway) for the subject, queue, claim and
actor model.
