# Moving to a gateway

One gateway holds every inbound transport for a fleet of instances — the GitHub and Jira
webhooks, one Slack Socket Mode connection per app, the pollers — and each instance polls
its own queue ([the capability](../capabilities/gateway.md), issue-496). This page is the
move: an instance that today runs its own poller or Slack listener, put behind a gateway.
Nothing migrates by itself, because the gateway is **opt-in**: a `cli-config.yaml` without
a `gateway` block behaves exactly as before, and no key was renamed or removed.

## When you want one

- Two or more instances read **one Slack app**. Slack splits an app's envelopes across its
  open connections, so two listeners each hear half; the gateway holds the one connection.
- Two or more instances poll **the same repositories**, each spending the API budget and
  each able to arm the same item.
- A GitHub webhook should reach several instances, and only one URL can be registered.

One instance on one machine gains nothing from a gateway; leave it as it is.

## The move

1. **Write `gateway-config.yaml`** beside the CLI config of the machine that will run the
   gateway. `/the-loop:init` asks *"will this instance read its events from a gateway?"*
   and, when you say the gateway runs here, scaffolds the file; by hand, start from
   `templates/gateway-config.yaml` in the plugin. Every secret is an environment-variable
   **name** (`*Env`) read from `env.file`: the GitHub poll token (read access only), the
   Slack app-level token and bot token. They move to the gateway; the gateway holds no
   posting token and spawns nothing. List the repositories (`repositories`,
   `github.poll.sources`) and, for Slack rooms, the `slack.rooms` entries the instances
   declared.
2. **Start it**: `the-loop gateway start`. It validates the file, refuses to start on a
   violation naming each key, and listens on `127.0.0.1:8790` by default. A non-loopback
   `listen.host` needs `listen.exposed: true` — there is no instance authentication in
   this release, so the network is the boundary
   ([decision-146](../decisions/decision-146.md)).
3. **Point each instance at it.** Add the [`gateway` block](../config/cli/gateway-options.md)
   to the instance's `cli-config.yaml` — `url`, and `actors` for the users this instance
   works for — give the instance a distinct `instance.name` (a second peer under a live
   name is refused with `409`), and `the-loop restart`. From then on its `webhooks`,
   `polling` and `channels.slack.read` blocks are ignored and `the-loop status` reads
   `off · gateway configured` for the three. Leave the blocks in place: remove the
   `gateway` block and the instance is exactly as before.
4. **Re-point a GitHub webhook**, if you had one, at the gateway's `/gh-webhook` with the
   same secret: the contract is GitHub's verbatim.
5. **Slack reads over Socket Mode only.** Behind a gateway there is no poll reader, so a
   reply in a bound thread is input only when it **mentions the bot** (the issue-389
   rule), and the app must hold `app_mentions:read` and subscribe to `app_mention`. An app
   installed before issue-389 lacks both: `/the-loop:upgrade-the-loop` regenerates the
   kept manifest and says when to re-apply it and reinstall, or run `the-loop channels
   manifest --write` yourself; `the-loop channels status --probe` lists the granted scopes.
6. **Check**: `the-loop gateway status` (ingresses, the Socket Mode state, live
   instances), `the-loop gateway instances` (each instance's lease, last fetch and
   backlog) and, on an instance, the Gateway card of the dashboard or
   `GET /api/v1/gateway`.

## What does not change

- The instance still spawns, posts, applies control commands and judges authorization;
  a forged event through the gateway is judged at the instance as it always was.
- Delivery ids are the ones the instance poller produced (`poll-comment-<id>`,
  `poll-presence-<ref>-<uuid>`), so the instance's dedup caches keep working.
- A running work item keeps running. The gateway baselines an item's existing thread at
  first sight, as the instance poller does: the history is never replayed as prompts.
  The one edge: a `the-loop start` posted before the gateway first listed the item is
  baselined too (the gateway runs no control grammar), so post it again.
- The gateway being unreachable stops nothing on the instance: it keeps running, retries
  with back-off and never falls back to its own ingresses.

## Not in this release

Partial hosting — an instance keeping its own GitHub poller with only Slack through the
gateway — is deliberately out: two pollers on one repository would arm the same item
twice, which is the duplication the gateway removes. A `gateway` block switches every
ingress of the instance off.
