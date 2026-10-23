<!-- Written per the `the-loop:writing` skill. -->

# Decision 151: The gateway posts to Slack for its instances with the token it already holds

- **Status:** proposed (the owner decides at the PR)
- **Date:** 2026-10-23
- **Deciders:** MadaraUchiha-314 (the requirements approval, the design review and its
  "just do a passthrough"), the-loop (the mechanism)
- **Work item:** [issue-519](https://github.com/MadaraUchiha-314/the-loop/issues/519)
- **Spec:** [`docs/specs/issue-519/`](../specs/issue-519/) (requirements D1–D5 and the
  amendment to R5; design § Architecture)
- **Amends:** [decision-146](decision-146.md): "the authorized-actor guard, the control
  grammar, the Slack allow-list and grants, and any posting token" stay on the instance —
  the last item is now "any GitHub or Jira posting token".

## Context

Behind a gateway an instance reads Slack through it but, until issue-519, wrote to Slack
with the app's bot token from its own environment. The gateway's Socket Mode adapter
cannot start without that same token, so the secret was on the gateway and on every
instance at once, while the guide said the gateway "holds no posting token". An instance
without the token started clean, reported the gateway connected, and posted nothing; the
only trace was a per-event warning and a growing undelivered line.

The first design registered each instance's channels on the gateway (home, rooms, bound
threads) and refused a post anywhere else. The owner rejected it at the design review:
too complicated, state in the gateway for a guard that is not authentication, and a
gateway failure should simply fail the post.

## Decision

- **The gateway posts for its instances, as a pass-through.** `POST
  /api/v1/gateway/slack/call {instance, peer, method, params}` makes one Slack Web API
  call with the bot token the gateway holds and returns Slack's status, body and
  `Retry-After` verbatim; `POST /api/v1/gateway/slack/download {url}` fetches a file under
  the instance's existing rules. Nothing is stored, queued or retried on the gateway.
- **Three checks, and the guards every consumer route has.** `slack.post.enabled`
  (default `true`, hot-reloaded), the token variable set, and the method in a flat
  allow-list of the fourteen Slack methods the instance calls; the `instances`
  allow-list and the peer lease as elsewhere. No channel registration.
- **Own token first on the instance.** One resolver picks the Slack client: the local
  bot token when set, else the gateway-backed client with the SDK's method names, else
  today's error with the gateway hint. A gateway that is unreachable or refuses fails the
  post; no fallback to a token, no retry of this change's own.
- **The instance says when nothing can post.** `start` warns once and still starts;
  `status`, `channels status` and `doctor slack` name the missing variable and what the
  gateway reports.
- **The boundary is unchanged and stated for posting.** No instance authentication
  (decision-146): any peer an exposed gateway accepts may post as the bot wherever the
  bot can see. The contract and the capability page say so; `slack.post.enabled: false`
  turns it off.

## Consequences

- One Slack secret for a fleet, on the gateway; an instance behind a posting gateway
  needs none. Every deployment with a local token behaves exactly as before.
- An exposed gateway now also lets a peer post as the bot. Loopback by default, the
  bearer-token attachment point of decision-146 covers this route too.
- Any new Slack call site on the instance is one more name in the allow-list, reviewed
  as such; the first enumeration missed `chat.getPermalink`, found by the integration
  scenarios.

## Alternatives considered

- **A per-instance channel registration on the gateway** (home channel, rooms, bound
  threads of claimed work items; `403 channel-not-registered`) — the first design.
  Rejected by the owner: state in the gateway for a guard that is not authentication.
- **A typed `POST /post` carrying event type, blocks and thread** (the reporter's
  sketch). Rejected: a second rendering path and a route per call site.
- **The loud failure alone** (the reporter's option 2). Rejected: leaves the bot token on
  every instance, which the reporter named as the point of gateway mode.
- **Gateway first, local token on failure.** Rejected: two credentials in play make a
  failure ambiguous.
