<!-- Written per the `the-loop:writing` skill. -->

# Decision 144: `gateway` names the ingress process; decision-059's gateway is the auth proxy in front of it

- **Status:** proposed (the owner decides at the PR)
- **Date:** 2026-10-19
- **Deciders:** MadaraUchiha-314 (the ask, the requirements and design gates), the-loop (design)
- **Work item:** [issue-496](https://github.com/MadaraUchiha-314/the-loop/issues/496)
- **Spec:** [`docs/specs/issue-496/design.md`](../specs/issue-496/design.md) §Overview, §Trade-offs

## Context

the-loop already uses the word *gateway* once. Decision-059 removed in-app
authentication from the control-plane service and said *"a gateway owns auth"*: an
auth-terminating reverse proxy an operator puts in front of the service when exposing
it. Issue-496 adds a process the author named **the gateway** too: one ingress for a
fleet — the webhooks, the one Slack Socket Mode connection per app, the pollers — that
stores every event and fans it out to the instances' queues. Two readings of one word,
both in the record, would send a reader of either decision to the wrong component.

## Decision

- **`gateway`, unqualified, is the ingress process of issue-496**: `the-loop gateway
  start|stop|status|restart|subjects|instances`, `gateway-config.yaml`,
  `gateway-config.schema.json`, the `gateway` block of an instance's CLI config, the
  `gateway.*` event family, the `the_loop.gateway` package and the
  `the-loop-gateway.v1.yaml` contract.
- **Decision-059's gateway is the *auth-terminating gateway*** — always written with
  that qualifier from now on, in docs and in code comments. It is a deployment's reverse
  proxy, not a the-loop process, and it may sit in front of the control-plane service
  **and** in front of an exposed the-loop gateway alike.
- The two are orthogonal: the ingress gateway carries no authentication of its own
  (decision-146) and expects the auth-terminating gateway, or the network boundary, to
  provide it.

## Consequences

- One word, two components, disambiguated by a qualifier rather than by renaming either:
  decision-059's text keeps reading as written, and the author's name for the new process
  stands.
- Every new page and record uses the unqualified word for the process; a reference to the
  proxy says *auth-terminating gateway* and links decision-059.

## Alternatives considered

- Rename the ingress process (`relay`, `hub`, `broker`) — the author named it, every
  ticket comment and the requirements use the name, and `broker` would wrongly promise
  Kafka-like semantics the design deliberately does not offer (one process, SQLite).
- Rename decision-059's gateway retroactively — rewriting an accepted record to make room
  for a new one inverts the record's purpose.
