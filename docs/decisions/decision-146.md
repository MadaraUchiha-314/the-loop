<!-- Written per the `the-loop:writing` skill. -->

# Decision 146: the instance-to-gateway boundary carries no authentication in this release; the exposure guard, the allow-list and the visible claims bound the gap

- **Status:** proposed (the owner decides at the PR)
- **Date:** 2026-10-19
- **Deciders:** MadaraUchiha-314 (the requirements gate, 2026-10-18: "no instance auth by decision"), the-loop (design)
- **Work item:** [issue-496](https://github.com/MadaraUchiha-314/the-loop/issues/496)
- **Spec:** [`docs/specs/issue-496/requirements.md`](../specs/issue-496/requirements.md) §Security considerations; [`design.md`](../specs/issue-496/design.md) §Security design
- **Refines:** [decision-059](decision-059.md) (the control-plane service carries no in-app authentication — the auth-terminating gateway owns it)
- **Amended by:** [decision-151](decision-151.md) (issue-519): "any posting token" below is now
  "any GitHub or Jira posting token" — the gateway posts to Slack for its instances with the bot
  token it already held, under this same boundary

## Context

The gateway's consumer API lets a peer fetch a queue, commit outcomes, claim a subject,
register actors and publish bindings. The requirements gate decided, as decision-059
did for the control-plane service, that this release adds **no** authentication between
an instance and its gateway: the first landing is one laptop, or one box, and a token
exchange would be a fourth secret to provision before the first event flows.

## Decision

- **No instance authentication.** Every consumer route is open to whoever can reach the
  socket. The gateway binds loopback by default; a non-loopback `listen.host` refuses
  to start unless `listen.exposed: true` is set — the control-plane service's own rule.
- **The boundary is the network, and the record says so.** The capability page's first
  paragraph and the OpenAPI document state that an exposed gateway is readable,
  claimable and committable by any peer on that network. An operator who exposes one
  puts the auth-terminating gateway of decision-059 in front of it, or keeps it on a
  private network.
- **Three guards bound the gap without being authentication:** the optional
  `instances` allow-list in `gateway-config.yaml` refuses an unknown instance name on
  fetch, claim and registration (a misconfiguration guard); a second peer under a live
  instance name is refused with `409 duplicate-instance` (the lease is per name, by
  peer, so two processes cannot split a queue silently); every claim and registration
  is recorded with its instance and time and listed by `gateway subjects` and
  `gateway instances`, so a misdirected work item is visible rather than silent.
- **What the gateway never holds:** the authorized-actor guard, the control grammar,
  the Slack allow-list and grants, and any posting token. Those stay on the instance;
  the gateway module tree imports neither the dispatcher nor the authorization module,
  and a test pins that import graph. A forged event through the gateway is therefore a
  forged event at the instance, judged as it always was.

## Consequences

- One laptop, one box, a private network: no setup beyond the `gateway` block.
- Exposed to the internet without a fronting proxy: anyone on that network can read a
  fleet's events, steer a subject to themselves by claim or registration, or commit
  deliveries unseen. Accepted for this release, stated in the docs, and bounded by the
  guards above.
- **The attachment point is fixed:** a bearer token named by environment variable,
  presented on every consumer call and checked where the `instances` allow-list is
  checked today, is the first follow-up when a deployment needs it — no route or shape
  changes.

## Alternatives considered

- A per-instance bearer token now — a fourth secret to provision and rotate before the
  first event, for deployments that are loopback in the first landing; deferred, with
  the attachment point named.
- mTLS between instance and gateway — heavier still, and the deployments that need it
  already run a proxy that terminates it.
- Signed envelopes — protects integrity, not access; the gap is who may fetch and claim.
