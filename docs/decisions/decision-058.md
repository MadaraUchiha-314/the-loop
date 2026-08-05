# Decision 058: Re-layer the CLI as core → HTTP API → clients; the service is the CLI's only execution path

- **Status:** proposed
- **Date:** 2026-08-05
- **Deciders:** @MadaraUchiha-314 (owner, via PR #162 phase-1 review), harness
- **Work item:** issue-161

## Context

Issue #161 asks for a control plane: every capability the CLI carries (poller,
webhook receiver, sessions, graph, events, repo-scoped queries) invocable by any
client — CLI, an agent over MCP, and a control-plane UI — through durable APIs.
The owner resolved the five architecture forks on the phase-1 review of PR #162:
a framework such as FastAPI is sanctioned; the CLI uses the service as its default
and **only** mode; the UI lives under `ui/` on Vite-class tooling, TypeScript only;
MCP is HTTP-only, no stdio; and delivery is a single PR.

## Decision

1. **Three layers.** A transport-agnostic `the_loop.core` facade (one module per
   capability, delegating to the existing modules) is the single implementation;
   `the_loop.api` (FastAPI) exposes it at `/api/v1` per an authored OpenAPI
   contract in `specs/openapi/`; the CLI, the MCP endpoint and the UI are thin
   clients of that surface.
2. **`[service]` extra.** `fastapi`/`uvicorn` are an optional extra; the base
   install keeps exactly `pyyaml`. Hosting a service requires the extra; a base
   install can still be a client of a running one (stdlib `urllib`).
3. **Service-only CLI with auto-start.** Core-capability commands have no
   in-process path. The CLI auto-starts a local service (pidfile + flock, the
   issue-159 lifecycle discipline) when none is reachable, keeping the
   one-command UX; bootstrap commands that manage the installation or the service
   process itself (`install`, `upgrade`, `migrate-config`, `service *`, `ui *`,
   `--version`) stay local.
4. **MCP as a ~150-line JSON-RPC endpoint** (`/mcp`) on the same app — HTTP only —
   whose tool registry is generated from the same core surface. The `mcp` SDK is
   rejected (multi-dependency chain for a protocol subset). Destructive/attribution
   -forging operations (`sessions reset`, `graph force`) are not exposed to agents.
5. **UI: Vite + vanilla TypeScript** under `ui/`, static-hostable build with a
   configurable API base; no component framework until the view count warrants one.

## Consequences

- Every capability becomes reachable programmatically, and new core capabilities
  are exposable over CLI/REST/MCP without duplicating logic.
- The base install's dependency footprint is unchanged, but *executing* core
  commands now requires the `[service]` extra to be present somewhere (locally for
  auto-start, or a reachable service) — a real behaviour change, gated fail-closed
  with an explicit install/start message.
- `check`'s purity contract moves to the core function; the CLI↔service hop is
  transport. CI environments run with the extra installed.
- The API is an RCE-equivalent surface and is treated as such: loopback-only by
  default, mandatory per-boot bearer token (0600, machine-local), pinned CORS.

## Alternatives considered

- **stdlib `http.server` service (zero new deps)** — rejected by the owner's
  framework sanction and by the cost of re-implementing validation/OpenAPI/ASGI
  lifecycle by hand.
- **In-process fallback when no service runs** — rejected by the owner: the
  service is the only mode; a fallback would fork behaviour across two paths.
- **MCP via the official SDK / stdio transport** — stdio rejected by the owner;
  the SDK rejected on the minimalism ladder.
- **React (or similar) UI** — deferred; three views need no framework, and the
  TS-only rule is independent of framework choice.
