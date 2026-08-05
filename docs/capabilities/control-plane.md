# Capability: control plane

> The API layer over the-loop's core, and its clients: the service-routed CLI,
> the MCP endpoint, and the statically-hostable UI (issue-161, decision-058).

## What it is

the-loop's executable functionality is layered as **core → API → clients**: a
transport-agnostic core facade (`the_loop.core`, one module per capability) is the
single implementation; the API service (`the_loop.api`, FastAPI behind the
`[service]` extra) exposes it at `/api/v1` plus an MCP endpoint at `/mcp`; the CLI,
an agent host and the `ui/` frontend are thin clients of that surface.

## Current behaviour

- The core facade SHALL be importable and invocable with no CLI or HTTP context;
  every capability (work items, events, graphs, repo-scoped queries, sessions,
  daemons, attention) SHALL be implemented once there, delegating to the modules
  that already carry the behaviour.
- The API service SHALL expose the core at `/api/v1` per the **authored OpenAPI
  contract** (`specs/openapi/the-loop.v1.yaml`); a parity test SHALL fail the build
  when the served schema's paths/methods/operationIds drift from it. Interactive
  docs are served at `/api/docs`, generated, never hand-written.
- The service SHALL bind loopback by default and refuse a non-loopback bind unless
  `service.exposed: true`; every route except `/api/v1/health` SHALL require the
  per-boot bearer token (32-byte urandom, 0600 under `<state.root>/local/`,
  constant-time compared, never returned by any API); CORS SHALL be pinned to
  `service.ui.origins`. An empty token SHALL reject everything — fail closed, never
  open.
- `the-loop service start|stop|status` SHALL manage the service with the issue-159
  lifecycle discipline: the pidfile is the flock, a second start reports `already
  running`, stop signals and waits. Hosting requires the `[service]` extra
  (fastapi + uvicorn); the base install keeps exactly `pyyaml`.
- The service SHALL be the CLI's **only execution path** for core capabilities
  (owner decision, PR #162): a command auto-starts a local service when
  `service.autoStart` allows and otherwise fails closed naming `the-loop service
  start` and the install line — never an in-process fallback. Bootstrap commands
  (`install`, `upgrade`, `migrate-config`, `service`, `ui`, `--version`) and the
  destructive `sessions reset` stay local. `THE_LOOP_SERVICE_LOCAL=1` marks the
  service's own invocations into its CLI (loop prevention). *(Transitional:
  `check` and `events` route today; the remaining commands' entry points are being
  switched over — the service-side surface is complete.)*
- `/mcp` SHALL serve the MCP interface over **HTTP transport only** (no stdio):
  `initialize`, `tools/list` and `tools/call` over the same core facade, with the
  same bearer token. `sessions reset` (destructive) and `graph force` (requires a
  human-attributed reason) SHALL NOT be exposed as tools.
- Every API operation SHALL land in the event log (`api.request`; rejections as
  `api.auth.denied`; tool calls as `mcp.call`), queryable via
  `the-loop events --source service`.
- The UI under `ui/` SHALL be TypeScript only, built with Vite to **static assets**
  (relative base) with the API base configurable at build time (`VITE_API_BASE`)
  and runtime (`?api=`, remembered); the bearer token is entered in the UI and held
  in localStorage. It SHALL surface the work items in flight, a work item's detail
  (session controls + event trail), and the needs-attention list. `the-loop ui
  dev|build` delegate to `npm --prefix ui` as an argv list, never a shell.

## Design

[`docs/specs/issue-161/design.md`](../specs/issue-161/design.md) ·
[`specs/openapi/the-loop.v1.yaml`](../../specs/openapi/the-loop.v1.yaml) ·
[CLI: service](../cli/commands/service.md) · [CLI: ui](../cli/commands/ui.md) ·
[config: service options](../config/cli/service-options.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-161 | Capability minted: core facade extracted, API service + OpenAPI contract, token-auth + loopback-default security posture, service lifecycle commands, service-routed CLI (check/events first), HTTP-only MCP endpoint, Vite+TS control-plane UI | [spec](../specs/issue-161/), [decision-058](../decisions/decision-058.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/161) |
