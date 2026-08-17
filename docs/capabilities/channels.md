# Capability: channels

> the-loop holds a back-and-forth conversation on surfaces beside the work item —
> starting with a Slack bot that writes *and* reads — while the work item stays the
> single source of truth.

## What it is

The conversation layer: a channel is a named surface with its own event-type filter and
verbosity that carries the-loop's questions out (`the-loop ask` fans out after the
work-item post) and, for channels that can read, carries the answers back in. Every
answer is mirrored onto the work item as the-loop's own marker-stamped comment, so the
ticket remains the record whatever surface the human actually used. Distinct from the
integrations layer ([issue-109](https://github.com/MadaraUchiha-314/the-loop/issues/109)):
an integration is a transport for one call; a channel is a conversation with state.

## Current behaviour

- Channels are configured under `channels` in the CLI config
  ([channels options](/config/cli/channels-options)); the section is optional, and WHEN
  it is absent THEN behaviour SHALL be exactly the pre-channels behaviour. A malformed
  section SHALL resolve to disabled with a logged error — fail closed, never
  half-enabled.
- WHEN `the-loop ask` records a question THEN it SHALL first post it on the work item
  (unchanged), and then broadcast it to every enabled channel whose `events` allow-list
  includes `session.awaiting_input`, rendered at the channel's `verbosity`
  (`quiet` ⊂ `normal` ⊂ `verbose`). Channel delivery SHALL be best-effort: an outage
  never changes the ask's outcome or exit code.
- WHEN the graph's `notify` hook fires for a notification event THEN it SHALL
  broadcast through the same channels and the same `events` filter — a channel
  subscribed to `phase-approval-pending` carries it, one that is not reports a skip.
  `integrations.slack` no longer exists; resolving it is a named refusal pointing at
  `channels.slack`, and `the-loop migrate-config` (config version 0.5.0) retires an
  old section.
- The Slack bot channel SHALL post through the official `slack-sdk` `WebClient` with a
  bot token read **at call time** from the env var named by
  `channels.slack.botTokenEnv` (default `THE_LOOP_SLACK_BOT_TOKEN`); one Slack thread
  SHALL carry one work item's conversation, and the binding (thread → work item) SHALL
  be recorded in local state (`<state.root>/channels/slack.json`, bounded). Token
  values SHALL never appear in config, state, status output or the event log.
- Replies SHALL be read **with or without polling**: `read.mode: poll` fetches new
  thread replies on a background thread inside the poller and gh-webhook daemons (and
  `the-loop channels poll` runs one cycle synchronously); `read.mode: socket` receives
  them over Slack **Socket Mode** via `the-loop channels listen` (an outbound
  connection — no exposed endpoint); `off` reads nothing. Both transports SHALL read
  only threads the-loop itself started, and SHALL share one per-thread cursor so a
  reply is processed at most once, across restarts and mode switches.
- WHEN a reply arrives THEN the pipeline SHALL run map → drop-own → authorize →
  mirror → deliver: a message outside a bound thread is dropped `unmapped`; a
  bot-authored message (the-loop's own included) is dropped before authorization; a
  reply whose Slack **member id** is not in `channels.slack.authorizedUsers` is
  dropped — not mirrored, not delivered — and an empty allow-list denies everyone
  (fail closed).
- WHEN a reply is accepted THEN it SHALL be mirrored onto the work item **first** —
  the-loop's own comment quoting the reply (scrubbed, control-keywords defanged),
  with a visible attribution naming the channel and author and the self-authored
  marker, so both ingress paths drop it and nothing is processed twice — and then
  delivered into the waiting session through the same fail-closed path the reply
  route uses (never spawning, respawning or resuming). WHEN delivery fails THEN the
  mirror stands as the answer of record.
- Every step SHALL be observable as registered `channel.*` event types (`posted`,
  `post_failed`, `reply_received`, `dropped` with a machine-readable reason,
  `mirrored`, `mirror_failed`); payloads carry ids, never message text.

## Design

- [`docs/specs/issue-245/design.md`](../specs/issue-245/design.md) — the channel
  contract, the Slack provider, the inbound pipeline and its ordering, the two read
  transports, and the security design table.
- [`skills/the-loop/reference/collaboration.md`](https://github.com/MadaraUchiha-314/the-loop/blob/main/skills/the-loop/reference/collaboration.md)
  § Where questions go — how channels compose with the interaction mode and the
  self-comment marker rule.
- The `notify` graph hook posts **through channels** (decision-094 D8, the owner's
  convergence call on PR #267): a graph notification is one more outbound event,
  filtered by each channel's `events` allow-list, so notifications gain the reply path
  for free. The old `integrations.slack` incoming webhook is retired — a config still
  carrying it is refused, and `the-loop migrate-config` removes it.
  [`decision-094`](../decisions/decision-094.md) records the split and the remaining
  deferrals (per-collaborator targeting, more channel types).

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-245 | Introduced the capability: the channel abstraction (events filter, verbosity, best-effort broadcast from `the-loop ask`), the Slack bot channel (slack-sdk, thread per work item, poll + Socket Mode reads), the authorize → mirror → deliver inbound pipeline with the work item as source of truth, the `channels` CLI verb, and the `channel.*` event types. In the same PR's review the owner converged Slack entirely onto this layer: the graph's `notify` hook broadcasts through channels and `integrations.slack` (the incoming webhook) was removed behind a versioned migration (0.5.0). | [spec](../specs/issue-245/), [decision-094](../decisions/decision-094.md), [PR #267](https://github.com/MadaraUchiha-314/the-loop/pull/267) |
