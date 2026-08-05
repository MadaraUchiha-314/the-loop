# Decision 059: The control-plane service carries no in-app authentication — the gateway owns auth

- **Status:** proposed
- **Date:** 2026-08-05
- **Deciders:** @MadaraUchiha-314 (owner, via [PR #162 comment](https://github.com/MadaraUchiha-314/the-loop/pull/162#issuecomment-5194359297)), harness
- **Work item:** issue-161

## Context

The first cut of the control-plane API service (decision-058) authenticated every
route with a per-boot bearer token (0600 file, constant-time compare, fail-closed),
because the service is remote-code-execution-equivalent — a call can spawn a harness
session with the operator's credentials. The security-review gate then found a HIGH
in the UI's handling of that token (exfiltration via a poisoned `?api=` link), which
was fixed by pinning the token to allowlisted origins.

On review, the owner directed a different model: **remove in-app authentication for
now — the gateway under which the service is deployed will handle auth.** The service
is expected to run behind an auth-terminating gateway (or on loopback for local use),
so authenticating callers a second time inside the service duplicates a concern the
deployment already owns.

## Decision

The service performs **no authentication of its own**. Concretely:

- The bearer-token layer is removed end to end: no token minting (`api/auth.py`
  deleted), no `Authorization` check on any route or on `/mcp`, no token in the CLI
  client or the UI. `api.auth.denied` is retired from the event catalog.
- The service's own boundary is **network scoping**: it binds `127.0.0.1` by default
  and the exposure guard in `serve.py` still refuses a non-loopback bind unless
  `service.exposed: true`. A real deployment sets `exposed: true` **and** puts an
  auth-terminating gateway in front.
- CORS stays pinned to `service.ui.origins`; input validation, the argv-no-shell
  critic runner, and the MCP exclusions (`sessions reset`, `graph force`) are
  unchanged — those are not authentication.

Supersedes decision-058's token-auth posture (that decision otherwise stands).

## Consequences

- Simpler surface: no credential to mint, store, rotate, or leak — which also
  **resolves the security-review HIGH at its root** (no token exists to exfiltrate),
  beyond the origin-pinning that first fixed it.
- The safety of an *exposed* deployment now rests entirely on the fronting gateway
  and the `exposed` opt-in. Exposing the service on a network **without** a gateway
  would leave an unauthenticated RCE-equivalent endpoint open — the exposure guard
  makes that a deliberate, explicit act, and the docs say so plainly.
- Local use is unchanged and simpler: loopback-only, no token to copy into the UI.
- The tier-4 security sign-off now covers this posture (network boundary + gateway),
  not a token scheme.

## Alternatives considered

- **Keep the per-boot bearer token** (decision-058) — rejected by the owner in favor
  of the gateway-owns-auth deployment model; it duplicated the gateway's job.
- **Pluggable auth (token *or* gateway, configurable)** — rejected as YAGNI for now:
  the owner's stated model is gateway-fronted, and a config toggle would carry two
  code paths and two threat models for a choice not yet needed. Revisit if a
  no-gateway exposed deployment becomes a real requirement.
