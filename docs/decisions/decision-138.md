# Decision 138: a manager is the worker's router over a fleet facade — `instance.role: manager`, a registry in `cli-config.yaml`, members trusted by name, ambiguity refused

- **Status:** proposed
- **Date:** 2026-09-29
- **Work item:** [issue-374](https://github.com/MadaraUchiha-314/the-loop/issues/374)
- **Deciders:** MadaraUchiha-314 (the ask), the-loop (design); MadaraUchiha-314 (owner,
  at the spec gate and the PR)
- **Refines:** [decision-110](decision-110.md) (an instance is a named, scoped CLI
  config; the manager is a client, not a peer protocol), [decision-059](decision-059.md)
  (the plane carries no in-app auth), [decision-087](decision-087.md) (the stream is SSE)

## Context

Since issue-322 an operator can run several instances of the-loop, each a named, scoped
`cli-config.yaml` serving one identical `/api/v1` at its own address; the dashboard takes
one address. Issue-374 asks for a **manager**: an instance whose config says it manages
others, which serves the same API so the dashboard needs no change, whose registry of
instances is editable from the dashboard and from a hot-reloaded file through one code
path, and a new tab to see and manage each instance.

Decision-110 D8 left the seams — one identical surface per instance,
`GET /api/v1/instance` naming each, `control.instance` on every record — and said the
manager would be a client of N base URLs.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The role is `instance.role` in `cli-config.yaml`**, and the registry is `instance.manager.instances[] {name, url}` in the same block. | Decision-110 D1: an instance *is* a running CLI config, so the file that names it names its role. The registry is three keys away from the name it qualifies. |
| D2 | **A manager is also a worker, and its own first member**: `role: manager` adds the fleet beside the worker's responsibilities and removes none; the manager's own state is served in-process under its own name, never registered as a URL. | The owner's call at the spec gate (PR #436): an instance that becomes a manager keeps its worker responsibilities. It also keeps the config small and the fleet flat — a box that both manages and works runs one instance, not two. |
| D3 | **One router, two facades**: `routes.build_router(holder, facade=…)` and `mcp.build_server(…, facade=…)`; the worker's facade is `the_loop.core`, the manager's is `the_loop.manager.facade` with the same function names and signatures. | "Exactly the same API surface" becomes a property of construction, and the contract parity test proves it for both applications. A second router would drift; a reverse proxy could not aggregate. |
| D4 | **The registry is a config key written through the config route**: `POST /instances/register` and `/unregister` — and the CLI's `the-loop instances register` and `unregister`, thin clients of them — call `core.config.update_config` with a sparse patch; the file is the only store. | The ask's "both should converge to the same code path": a hand edit and a dashboard edit are indistinguishable in the file, reach the service through the one per-request refresh, and inherit the splice's comment preservation, validation and atomic write. |
| D5 | **A member is trusted by its name, checked at probe**: `GET /instance` must answer with the registered `name` and `role: worker` before anything is served from or sent to it; an unnamed worker cannot be a member. | A URL is an address, not an identity. A re-used port, a wrong host or a redirect must not hand another box's sessions to the board or the board's commands to another box. |
| D6 | **Ambiguity refuses**: a key that resolves to two members is `409` naming them, never first-registered-wins, unless `instance` names one. | Issue-322 allows a work item declared on two instances; a `stop` sent to the first, or to both, is the two-daemons-steering-one-item failure decision-110 D6 avoided. |
| D7 | **The `instance` parameter is part of the one contract**, optional on every keyed operation; a worker accepts only its own name. | A client need not know which role it talks to; the same dashboard bundle drives a worker and a manager, and "manage one instance individually" is one parameter, not a second surface. |
| D8 | **The stream is a fan-in of member streams** with a per-member cursor (`name=offset,…`), one upstream per live member however many subscribers. | Polling members for events would re-create the latency issue-239 removed; a composite cursor keeps lossless resume per member, and the existing broker keeps the subscriber bound. |
| D9 | **The `instances` family is served by every role** — a worker answers with itself. | One renderer and one code path in the dashboard; the tab is not a manager-only feature that a lone operator must be told to ignore. |
| D10 | **The client is stdlib on threads**; no new dependency. | `the_loop.client` is already `urllib`; a bounded pool and one thread per upstream stream cost nothing the package does not already carry. |
| D11 | **An unknown role or an unnamed manager refuses to boot**, before the bind and the run lock. | A mistyped role must neither silently spawn sessions (the worker reading) nor silently manage nothing (the manager reading); the `service.cors` refusal is the precedent. Every other reader warns and reads `worker`, so `status` still answers. |

## Consequences

**Good.** The dashboard points at one URL and sees the fleet as one instance, each row
saying which instance owns it; an operator adds a box from the tab or the file and gets
the same result; one instance is managed on its own with one parameter; a member that
answers wrongly is never trusted; the surface cannot drift because there is one of it.

**Costs, accepted.** A manager's box serves two kinds of load; a keyed operation costs a cached probe plus
a call; 30 operations gain an optional parameter; a worker describes itself on a route a
lone operator will not need; the dashboard's row key becomes `instance@ref`; whoever
reaches the manager reaches every member's config and restart — the reach is the point,
and the guide names it.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| A top-level `manager` block, or a separate `fleet.yaml` | A second place for what the `instance` block already qualifies; a second file outside the reload and the config route (D1, D4) |
| A manager that does no work (a pure aggregator) | The owner's decision at the gate: a manager keeps its worker responsibilities (D2); a pure aggregator would also mean a second process on any box that both manages and works |
| A second router for the manager | Drift; the parity test would prove only that the files matched on the day they were written (D3) |
| A reverse proxy in front of N instances | Cannot aggregate a list read or route a keyed one; every path would need a prefix, which is the second surface the ask forbids |
| An in-memory registry with a `register` API, persisted separately | Two stores to reconcile; the ask's convergence would be a synchronisation problem (D4) |
| Trust by URL alone | A re-used address or a redirect is trusted; nothing checks that what answers is what was registered (D5) |
| First-registered-wins on an ambiguous ref | Two daemons steering one item, from one click (D6) |
| Per-instance routes (`/api/v1/instances/<name>/sessions/…`) | A second surface the dashboard would have to learn; `instance` as a parameter keeps one (D7) |
| Polling members for events | The latency issue-239 removed, times N (D8) |
| An async HTTP client (`httpx`, `aiohttp`) | A new dependency for one bounded pool and N long-lived reads (D10) |
| Unknown role narrows to `worker` | Fails open into spawning sessions on a typo (D11) |
| Members announcing themselves to a manager (discovery) | A second trust boundary and a second protocol with no requirement behind it; the operator registers |
