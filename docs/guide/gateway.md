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
- A GitHub webhook should reach several instances, and only one URL can be registered.
- No inbound webhook is possible at all (an enterprise network), so one process must
  hold the long-lived connections and poll on the fleet's behalf.

One instance on one machine gains nothing from a gateway; leave it as it is.

## The move

1. **Write `gateway-config.yaml`** beside the CLI config of the machine that will run the
   gateway. `/the-loop:init` asks *"will this instance read its events from a gateway?"*
   and, when you say the gateway runs here, scaffolds the file; by hand, start from
   `templates/gateway-config.yaml` in the plugin. Every secret is an environment-variable
   **name** (`*Env`) read from `env.file`: the GitHub poll token (read access only), the
   Slack app-level token and bot token. They move to the gateway; the gateway holds no
   posting token and spawns nothing. List the repositories (`repositories`) and, for
   Slack rooms, the `slack.rooms` entries the instances declared. The gateway's own
   GitHub and Jira pollers are **off** unless you turn them on (`github.poll.enabled`,
   `github.poll.sources`): your instances keep polling as they do today.
2. **Start it**: `the-loop gateway start`. It validates the file, refuses to start on a
   violation naming each key, and listens on `127.0.0.1:8790` by default. A non-loopback
   `listen.host` needs `listen.exposed: true` — there is no instance authentication in
   this release, so the network is the boundary
   ([decision-146](../decisions/decision-146.md)).
3. **Point each instance at it.** Add the [`gateway` block](../config/cli/gateway-options.md)
   to the instance's `cli-config.yaml` — `url`, and `actors` for the users this instance
   works for — give the instance a distinct `instance.name` (a second peer under a live
   name is refused with `409`), and `the-loop restart`. Its webhook receiver and its
   poller keep running exactly as `webhooks` and `polling` say; only its Slack listener
   (or poll reader) stops, and `the-loop status` reads `off · gateway configured` for
   it. Remove the `gateway` block and the instance is exactly as before.
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
- A running work item keeps running: your instance's poller still reads its ticket.
  If you do turn the gateway's poller on, it baselines an item's existing thread at
  first sight, as the instance poller does, so a history is never replayed as prompts;
  the one edge is a `the-loop start` posted before the gateway first listed the item,
  which is baselined too (the gateway runs no control grammar), so post it again.
- The gateway being unreachable stops nothing on the instance: it keeps running, retries
  with back-off and never falls back to its own ingresses.

## Who polls

Each instance keeps its own GitHub and Jira pollers behind a gateway; that is the P0 of
the first landing, so a fleet never funnels every work item's polling through one
process. An instance that polls a repository itself *and* receives that repository's
webhooks through the gateway sees a comment by both paths, exactly as an instance
running its own receiver beside its own poller does today, so pick one per repository.
Slack is the gateway's alone: one app has one Socket Mode connection.
