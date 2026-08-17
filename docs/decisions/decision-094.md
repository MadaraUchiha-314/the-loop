# Decision 094: channels are a conversation layer beside the integrations, and the work item stays the source of truth

- **Status:** proposed
- **Date:** 2026-08-17
- **Work item:** [issue-245](https://github.com/MadaraUchiha-314/the-loop/issues/245)
- **Deciders:** MadaraUchiha-314 (owner, via the ticket), the-loop (proposal)
- **Refines:** [decision-042](decision-042.md) (integrations: two call planes),
  [decision-035](decision-035.md) (collaborators own their notification channels)

## Context

the-loop could talk *at* Slack and not listen: the whole Slack surface was the
incoming-webhook `post-message` fired by the graph's `notify` hook. Every real
back-and-forth ran through work-item comments. Issue-245 asks for channels as an
abstraction — each with its own event filter and verbosity, the `ask` fanning out to
all of them, a Slack **bot** (owner's comment: the Python SDK) reading and writing with
and without polling — under one invariant: whatever surface carries the conversation,
the work item is the single source of truth, and a reply arriving through a channel is
posted back onto it under the-loop's magic marker so it is never processed twice.

## Decision

| Sub-decision | What was chosen | Why |
|--------------|-----------------|-----|
| D1 | A new `channels` CLI-config section and `the_loop/channels/` package — **not** an extension of `integrations.slack` | An integration is a transport for one call; a channel adds an event filter, verbosity, an inbound allow-list and conversation state. One schema shape cannot carry both without every key turning conditional. *(Amended by D8: the webhook integration is removed, not kept.)* |
| D2 | Outbound rides `the-loop ask`: work item first, then a best-effort broadcast | The ticket names the ask explicitly ("when the-loop uses ask command, it goes through all the channels"), and R1.2 pins the ordering: a channel outage must never change the ask's outcome. |
| D3 | Inbound converges on the **reply path**, not the event path | The poller's provider seam synthesises GitHub-webhook-shaped payloads; a Slack reply forced through it would impersonate a GitHub comment (actor semantics, authz, reactions all read GitHub keys). `reply_session`'s fail-closed contract (never spawn, refuse paused) is inherited instead of re-implemented. |
| D4 | The mirror is marker-stamped and lands **before** delivery | The marker makes the mirror inert at ingress (the issue-64/104 contract, zero new machinery), which is exactly the ticket's "not processed twice" rule; mirroring first means the decision reaches the source of truth even when no session is left. |
| D5 | Inbound authorization is a fail-closed allow-list of Slack **member ids** | A reply delivered into a session is an instruction to an agent, and a mirror is a ticket write under the operator's credentials. Empty list = deny all, the `routing.authorizedUsers` posture; ids not display names, because names are attacker-chosen. |
| D6 | Reads: `poll` (a daemon background watcher + `channels poll` for cron) and `socket` (Socket Mode via `channels listen`) | The ticket requires both with- and without-polling. Socket Mode is an outbound connection in the SDK the project already ships — push without exposing an HTTP endpoint. The listener is its own verb because a WebSocket's reconnect lifecycle does not belong inside a poll loop. |
| D7 | Tokens are env-named (`botTokenEnv`/`appTokenEnv`), read at call time, never values | The `secretEnv`/webhook-URL arrangement the ticket itself points at, applied twice; values never reach config, state, status output or the event log. |
| D8 | **Converge now** (owner's review call on [PR #267](https://github.com/MadaraUchiha-314/the-loop/pull/267): "converge right now. no one is using the webhook integration"): the graph's `notify` hook broadcasts through channels, `integrations.slack` is removed, and a config still carrying it is refused with the replacement named (`the-loop migrate-config`, version 0.5.0) | The original plan kept the webhook as a transitional second surface; the owner priced the transition at zero users and chose one Slack config over compatibility with nobody. Notification events flow through each channel's `events` allow-list, so notifications gain the reply path for free. Supersedes [decision-075](decision-075.md) (the inline-URL carve-out belonged to the removed integration). |

## Consequences

**Good.** A second conversation surface with zero new loop-prevention machinery; the
next channel type is a provider behind an existing contract; every step is observable
(`channel.*`); nothing changes for a config without a `channels` section.

**Costs, accepted.** Removing `integrations.slack` (D8) is a breaking config change —
priced at zero known users by the owner and made safe by the versioned migration; a
graph notification now requires the bot to be configured (a webhook URL alone no longer
delivers anything), and the notification events must be added to the channel's `events`
list. Per-collaborator targeting (`collaborators[].notifications.channels`) remains
declared-but-unread; channels give it a transport to eventually target. Thread
bindings are per-machine, so a deployment move drops open conversations (recorded,
harmless — new asks start new threads).

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Keep `integrations.slack` beside `channels.slack` as a transition | The design's original shape, rejected in review: two Slack configurations to document and distinguish, protecting compatibility no deployment uses. |
| Extend the poller's `PollProvider` with a Slack source | Its payloads must be GitHub-webhook-shaped; a Slack reply through it impersonates a GitHub comment and authz silently lies. |
| Post channel replies onto the ticket unmarked and let ingress process them | Violates the ticket's marker rule, doubles the processing path, and misattributes the reply to the operator's GitHub identity. |
| A Slack Events-API HTTP receiver | A second exposed endpoint plus signing-secret machinery for what Socket Mode does over an outbound connection; add it if a deployment ever needs it. |
| Wire `collaborators[].notifications.channels` now | Role resolution and per-person routing are real scope, orthogonal to the transport; the config shapes stay compatible for the follow-up. |
