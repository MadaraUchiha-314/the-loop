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
   contract in this repo's `apiSpecs.rest.dir` (`docs/api-specs/openapi/`, an
   override of the shipped `specs/openapi` default — owner decision on PR #162);
   the CLI and the MCP endpoint are thin clients of that surface. *(A UI client
   was part of this decision as drafted; it was descoped from issue-161 on owner
   review and deferred to a follow-up work item.)*
2. ~~**`[service]` extra.** `fastapi`/`uvicorn` are an optional extra; the base
   install keeps exactly `pyyaml`.~~ **Superseded on owner review (PR #162):**
   *"No extras pls. It creates a nightmare when installing. All deps get
   installed when one installs the-loopy-one."* `fastapi`, `uvicorn`, `mcp` and
   `slack-sdk` are **required** dependencies; the published extra names survive as
   empty no-ops so pinned install lines keep resolving. The MCP SDK's floor moves
   the package to Python 3.10+.
3. **Service-only CLI with auto-start.** Core-capability commands have no
   in-process path. The CLI auto-starts a local service (pidfile + flock, the
   issue-159 lifecycle discipline) when none is reachable, keeping the
   one-command UX. What stays local is local **by nature**: the bootstrap
   commands that manage the installation or the service process itself
   (`install`, `upgrade`, `migrate-config`, `service *`, `--version`),
   `sessions attach` (it execs tmux onto the caller's terminal), `sessions reset`
   (recovery must work when nothing is running), and `poll start` /
   `gh-webhook start` (foreground daemons that cron and systemd units depend on —
   the detached path is `/api/v1/daemons`).
4. ~~**MCP as a ~150-line JSON-RPC endpoint** whose tool registry is generated
   from the core surface; the `mcp` SDK rejected on the minimalism ladder.~~
   **Superseded on owner review (PR #162):** *"I hope we are using the official
   python SDK for MCP… Don't want to maintain custom implementation. Follow
   official SDKs."* `/mcp` is served by the **official** `mcp` SDK, mounted on the
   same app; this repo keeps only the binding from core to `add_tool`. HTTP
   transport only (no stdio) is unchanged, as is the exclusion of
   destructive/attribution-forging operations (`sessions reset`, `graph force`).
5. **UI: Vite + vanilla TypeScript** under `ui/`, static-hostable build with a
   configurable API base; no component framework until the view count warrants one.

## Consequences

- Every capability becomes reachable programmatically, and new core capabilities
  are exposable over CLI/REST/MCP without duplicating logic.
- The install grows four required dependencies and a Python floor of 3.10, and in
  exchange there is nothing to remember: one `pip install the-loopy-one` can host
  the service, serve MCP and use every transport. *Executing* a core command now
  needs a reachable service (auto-started by default) — a real behaviour change,
  gated fail-closed with an explicit `the-loop service start` message.
- `check`'s purity contract moves to the core function; the CLI↔service hop is
  transport.
- The CLI stops being an implementation: it renders the `messages` and `exitCode`
  the core facade returns, so an operator's command, an HTTP call and an MCP tool
  call produce the same words from the same code.
- The API is an RCE-equivalent surface and is treated as such: loopback-only by
  default, no CORS headers. *(The per-boot bearer-token auth this decision originally
  specified was **superseded by [decision-059](decision-059.md)**: the service
  carries no in-app auth — a gateway owns it — and its own boundary is network
  scoping via the exposure guard.)*

## Alternatives considered

- **stdlib `http.server` service (zero new deps)** — rejected by the owner's
  framework sanction and by the cost of re-implementing validation/OpenAPI/ASGI
  lifecycle by hand.
- **In-process fallback when no service runs** — rejected by the owner: the
  service is the only mode; a fallback would fork behaviour across two paths.
- **MCP via stdio transport** — rejected by the owner; HTTP only. *(The
  accompanying rejection of the official SDK was itself later reversed by the
  owner — see decision 4 above.)*
- **React (or similar) UI** — deferred; three views need no framework, and the
  TS-only rule is independent of framework choice.
