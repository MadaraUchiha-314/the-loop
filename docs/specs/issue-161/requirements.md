---
type: requirements
phase: requirements-definition
workItem: "issue-161"
status: approved             # drafting-side lock; the human phase gate is the spec-PR approval (tier 4)
approvedBy: []               # filled from the PR approval (paper trail)
riskTier: 4                  # re-architects the whole CLI surface; adds a network API, an MCP surface and a UI (new attack surface)
collaborators: [product-manager, architect, engineer, designer]
overrides: {}
---

# Requirements: control plane and API layer for the-loop

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.
>
> **Program note:** [issue #161](https://github.com/MadaraUchiha-314/the-loop/issues/161)
> is an architecture **program**, not a single change: it re-layers ~18.5k lines of CLI
> code and adds two new interfaces (HTTP API + MCP) and a UI. This spec defines the
> requirements for the whole program. Delivery is a **single PR** (owner decision on
> the phase-1 review, superseding the drafted sub-issue decomposition): `tasks.md`
> (Phase 3) still structures the work as a DAG, executed within this one PR.

## Introduction

the-loop today has two deliverables: the **plugin** (instructions Claude/Cursor follow
to run the PDLC) and the **CLI** (`the-loopy-one`), which carries all executable
functionality — the poller, the GitHub webhook receiver, session
management (register/list/attach/close/start/pause/resume/stop/reset), process-graph
management (`check`, `graph show|status|advance|run|force`), the event log,
scenarios/instructions/critic queries, and install/upgrade
([capability: cli](../../capabilities/cli.md)).

Every one of those features is reachable **only** by invoking the CLI on the machine
that holds the state. Issue #161 asks to re-architect this into three layers:

1. **Core functionality** — the existing behaviour, extracted so it is invocable as a
   library, transport-agnostic.
2. **API layer** — durable APIs over the core that any client can invoke.
3. **Clients** — the CLI becomes the first client of those APIs; **MCP** becomes a
   second API interface so an agent can control the-loop; a **control-plane UI**
   becomes the third client, surfacing what is in flight and what needs attention.

The core functionality must remain the same: this is a re-architecture, not a rewrite
of behaviour.

## Requirements

### Requirement 1 — three-layer architecture: core, API, clients

**User story:** As a maintainer of the-loop, I want the code organised as core
functionality, an API layer over it, and thin clients, so that every feature is
invocable by any client instead of being trapped inside CLI command handlers.

#### Acceptance criteria (EARS)

1. WHEN a capability exists in the-loop (polling, webhook ingress, session
   management, graph management, event-log queries, work-item state) THEN the system
   SHALL implement it once in a core layer that is importable and invocable without
   any CLI or HTTP context.
2. WHEN the API layer exposes a capability THEN it SHALL do so by delegating to the
   core layer, adding only transport, serialization, and authn/authz concerns.
3. WHEN a client (CLI, MCP, UI) needs a capability THEN it SHALL obtain it through
   the core or API layer; a client SHALL NOT carry business logic of its own.
4. IF a new capability is added to the core THEN the system SHALL make it exposable
   through every interface (CLI, HTTP API, MCP) without duplicating its logic.
5. WHILE the re-architecture proceeds, existing behaviour SHALL be preserved: the
   observable outcomes of every current command (state files written, comments
   posted, sessions spawned, events logged) SHALL be unchanged unless a requirement
   here explicitly changes them.

### Requirement 2 — the CLI keeps doing ALL the things it does today

**User story:** As a CLI operator, I want `the-loop` to keep every command and
behaviour it has today, so that the re-architecture never regresses my workflows.

#### Acceptance criteria (EARS)

1. WHEN any currently documented command is invoked (`gh-webhook`, `poll`,
   `sessions *`, `check`, `graph *`, `events`, `scenarios`, `instructions`,
   `critic *`, `install`, `upgrade`, `migrate-config`, `--version`) THEN the system
   SHALL provide the same behaviour, flags, exit codes and output formats as before
   the re-architecture.
2. WHEN any CLI command invokes a core capability THEN it SHALL perform the
   operation **through the API service** — the service is the default and ONLY
   execution mode (owner decision,
   [PR #162 review](https://github.com/MadaraUchiha-314/the-loop/pull/162#discussion_r3718672701));
   the CLI SHALL carry no in-process fallback path. `design.md` SHALL define how
   the CLI keeps today's one-command UX under this rule (service discovery, and
   auto-managing a local service where needed), because R2.1 (same behaviour,
   flags, exit codes) still applies.
3. IF no service is reachable and one cannot be made available THEN the CLI SHALL
   fail with a clear error naming the service lifecycle commands (R4) — never
   silently degrade to executing core logic in-process.
4. WHEN the re-architecture lands THEN existing test **coverage** SHALL be
   preserved — tests are adapted to exercise the service path (or the core layer
   directly) rather than deleted — and the config resolution order
   (`--config` / `$THE_LOOP_CLI_CONFIG` / repo-relative / home) SHALL be unchanged.

### Requirement 3 — durable API layer

**User story:** As a client author, I want durable APIs over the-loop's core, so that
any client — not just the bundled CLI — can drive the-loop programmatically.

#### Acceptance criteria (EARS)

1. WHEN the API service runs THEN it SHALL expose the core capabilities (work items,
   sessions, graph state, poller/webhook lifecycle and status, event-log queries)
   over HTTP. Authentication is out of the service's scope — it is the deploying
   gateway's responsibility (owner decision); the service binds loopback-only by
   default and refuses a non-loopback bind without explicit exposure config.
2. WHEN the API contract is authored THEN it SHALL be contract-first: an OpenAPI
   document under `specs/openapi/` SHALL be the source of truth, and API
   documentation SHALL be generated from it, never hand-written
   (`config.apiSpecs`, `reference/testing.md`).
3. WHEN the service restarts THEN no accepted operation SHALL be lost: API-visible
   state SHALL be backed by the same durable stores the CLI uses today (portable
   work-item records, session registry, event log), not by service memory.
4. WHEN a mutating operation is retried (client timeout, restart) THEN the system
   SHALL NOT double-apply it; idempotency SHALL follow the same discipline the
   poller's ledger already established (issue-159).
5. WHEN any API operation executes THEN it SHALL be recorded in the structured event
   log with the same observability discipline as existing routing/dispatch decisions
   (`reference/observability.md`).

### Requirement 4 — service lifecycle owned by the CLI

**User story:** As an operator, I want CLI commands to start and stop the API service
and the UI, so that running the control plane is as easy as running the poller today.

#### Acceptance criteria (EARS)

1. WHEN the operator runs the service start command THEN the system SHALL start the
   API service; WHEN the operator runs the stop command THEN the system SHALL stop
   it — with the same lifecycle discipline as existing daemons (pidfile+lock,
   idempotent stop/start, no zombie state; issue-159).
2. WHEN the operator wants the UI THEN the system SHALL provide a **separate**
   command to serve it (dev-server mode); the API service SHALL be startable
   without the UI and vice versa.
3. IF a start command is invoked while the component is already running THEN the
   system SHALL report that fact and SHALL NOT start a second instance against the
   same state.

### Requirement 5 — MCP as another interface over the same core

**User story:** As an agent harness (Claude etc.), I want the-loop's capabilities as
MCP tools, so that an agent can inspect and control work items, sessions and graphs
directly.

#### Acceptance criteria (EARS)

1. WHEN the core APIs exist THEN the system SHALL expose them through an MCP server
   as tools, reusing the core/API layer — MCP SHALL be an interface adapter, not a
   reimplementation — and the MCP transport SHALL be **HTTP only, no stdio** (owner
   decision, [PR #162 review](https://github.com/MadaraUchiha-314/the-loop/pull/162#discussion_r3718678832)).
2. WHEN the MCP surface is defined THEN each tool SHALL map to a core capability
   with the same access model (no in-app auth; the gateway's job) and the same
   event-log observability as the HTTP API.
3. IF a capability is intentionally not exposed over MCP (e.g. destructive resets)
   THEN that exclusion SHALL be recorded and justified in `design.md`.

### Requirement 6 — control-plane UI, statically hostable

**User story:** As a project owner, I want a control-plane UI showing what work items
are being worked on, each one's graph state, and what needs attention, so that
managing work items is easy without shell access.

#### Acceptance criteria (EARS)

1. WHEN the UI is built THEN it SHALL be statically hostable (e.g. GitHub Pages):
   the build output SHALL be plain static assets that talk to a configurable API
   base URL, with no server-side rendering required.
2. WHEN the UI is served in development THEN the dev-server command from
   Requirement 4 SHALL serve the same UI against a local API service.
3. WHEN the UI loads with a reachable API THEN it SHALL surface: the work items
   currently in flight, each work item's current phase/graph state, and the items
   needing attention (pending decisions/approvals, blocked gates, failed
   dispatches).
4. WHEN a work item is manageable THEN the UI SHALL offer the management operations
   the API exposes (e.g. the session start/pause/resume/stop verbs), each action
   producing the same paper trail as the equivalent comment keyword or CLI command.
5. WHEN visual design happens THEN it SHALL follow the design-artifact rules: the
   UI/UX design is iterated as self-contained HTML prototypes under
   `docs/specs/issue-161/design/` until locked with the designer
   (`design.uiArtifacts`, `reference/design-artifacts.md`).
6. WHEN the UI is implemented THEN all frontend assets SHALL live under a top-level
   `ui/` folder, SOTA tooling (e.g. Vite) MAY be used, and all frontend code SHALL
   be **TypeScript — no exceptions** (owner decision,
   [PR #162 review](https://github.com/MadaraUchiha-314/the-loop/pull/162#discussion_r3718677484)).

## Non-functional requirements

- **Minimalism / dependency budget.** The base CLI install currently has one required
  runtime dependency (`pyyaml`; `slack-sdk` as an extra). The API service and MCP
  server SHALL NOT change the base install's dependency footprint: anything beyond
  stdlib SHALL be an optional extra (as `slack` already is), and every new dependency
  SHALL be justified in `design.md` (`reference/minimalism.md`). The UI's frontend
  toolchain (Vite/TypeScript, owner-sanctioned) is scoped to `ui/` and does not
  affect the Python package's footprint.
- **Observability.** dev == runtime logging; every API/MCP operation lands in the
  structured event log and is queryable via `the-loop events`.
- **Testing.** Integration tests carry Gherkin docstrings with `Requirement:` links;
  API behaviour is tested against the OpenAPI contract.
- **Docs.** Command pages under `docs/cli/`, config keys under `docs/config/`, and
  the affected capability docs updated in the same PRs (existing parity tests keep
  holding).

## Security considerations

> Threat-model-lite (`security.threatModel.required`). This work item is the opposite
> of "no new attack surface": it deliberately creates three new surfaces (HTTP API,
> MCP, UI) over capabilities that can spawn agent sessions on the operator's machine.
> Risk tier 4 → the security review requires a named human sign-off
> (`security.review.humanSignOffMinTier: 4`).
>
> **Authentication model (owner decision, [PR #162](https://github.com/MadaraUchiha-314/the-loop/pull/162#issuecomment-5194359297)):**
> the service carries **no in-app authentication**. It is deployed behind a
> **gateway that terminates auth**, and locally it binds loopback-only by default.
> The service's own boundary is therefore **network scoping** (the exposure guard),
> not a credential. This deliberately supersedes the earlier bearer-token design
> (abuse case 1 below is retired accordingly).

- **Actors & trust:** the operator (trusted, owns the machine); the **gateway**
  fronting any exposed deployment (owns authn/authz); local clients on loopback
  (CLI, UI, MCP host); remote network peers (untrusted — reach the service only
  through the gateway); webhook payloads and work-item comments (untrusted, already
  HMAC-verified / authorized-user-gated today — those existing boundaries must
  survive the re-layering unchanged).
- **Trust boundaries & data:** the API service is a **remote-code-execution
  equivalent** — starting a session runs an agent harness with the operator's
  credentials. The service therefore SHALL bind to loopback by default; any
  non-loopback bind SHALL require explicit `service.exposed` configuration AND an
  auth-terminating gateway in front (the service does not authenticate callers
  itself). State it serves (portable records, session registry, event log) can
  embed repo paths and work-item metadata; no secrets/tokens SHALL ever be returned
  by any API. The static UI holds no credential of its own; it talks to whatever
  API base it is pointed at, and against a loopback-only service reached from
  elsewhere it simply shows nothing.
- **Abuse cases (EARS):**
  1. *(Retired — the service no longer authenticates; the gateway does. See the
     authentication-model note above.)*
  2. WHEN a request arrives on a non-loopback interface without the explicit
     exposure configuration THEN the system SHALL refuse to serve it (the exposure
     guard, enforced before binding).
  3. WHEN a hostile client attempts to use the API to run arbitrary commands (e.g.
     via crafted work-item refs, paths, or critic/config injection) THEN the system
     SHALL validate inputs against the same rules the CLI enforces today (argv
     lists, no shell; ref shape validation; schema-validated config) and reject
     what fails them.
  4. WHEN a browser context (the UI) talks to the API THEN cross-origin requests
     SHALL be constrained (CORS pinned to the configured UI origin), so a malicious
     web page cannot drive a local control plane.
  5. WHEN MCP tools are invoked by an agent THEN destructive operations SHALL be
     excluded or gated per R5.3, so a prompt-injected agent cannot silently wipe
     state.
- **Fail closed:** ambiguous/missing exposure configuration means loopback-only and
  refuse to bind beyond it; an unrecognised API version or malformed body is
  rejected, never best-effort interpreted. Because the service does not
  authenticate, exposing it without a gateway is the operator's responsibility — the
  exposure guard makes that a deliberate, explicit act.

## Out of scope

- **Agentic management of work items** — explicitly future scope in the issue.
- Changing what any core capability *does* (poller semantics, routing policy, graph
  gates); this is a re-layering.
- New ticketing providers (Jira APIs beyond what exists today).
- Hosting/deployment of the API service beyond the operator's machine (no SaaS).
- Retiring the plugin: the Claude/Cursor plugin remains the harness-side interface.

## Open questions

> Raised as a ticket comment on issue #161 (paper trail). These are **design-phase
> decisions**; they are listed here so the requirements reviewer can flag any that
> actually change scope.

1. ~~API style and stack: OpenAPI-documented REST over stdlib `http.server` (zero new
   required deps) vs. an optional-extra framework — where does the minimalism ladder
   land?~~ **Answered** (owner, [PR #162 review](https://github.com/MadaraUchiha-314/the-loop/pull/162#discussion_r3718668715)):
   a framework (e.g. FastAPI) is acceptable; the design phase picks one on its
   merits. The base install keeps its footprint — the framework lands behind an
   optional extra.
2. ~~Should the CLI *prefer* the service when one is running (auto-discovery), or only
   target it when explicitly told to?~~ **Answered** (owner,
   [PR #162 review](https://github.com/MadaraUchiha-314/the-loop/pull/162#discussion_r3718672701)):
   the CLI only uses the service — the default and ONLY mode. Folded into R2.2/R2.3.
3. ~~UI stack: how much UI is buildable as dependency-free static assets vs. a
   frontend toolchain (which would be the repo's first `package.json`)?~~ **Answered**
   (owner, [PR #162 review](https://github.com/MadaraUchiha-314/the-loop/pull/162#discussion_r3718677484)):
   SOTA tooling (e.g. Vite) is fine; all frontend assets under `ui/`; all frontend
   code is TypeScript, no exceptions. Folded into R6.6.
4. ~~MCP transport: stdio server spawned by the host (wrapping core in-process) vs. an
   adapter over the running HTTP service — or both?~~ **Answered** (owner,
   [PR #162 review](https://github.com/MadaraUchiha-314/the-loop/pull/162#discussion_r3718678832)):
   HTTP only, no stdio. Folded into R5.1.
5. ~~Delivery decomposition: which slices become sub-issues (suggested: core
   extraction, API service, CLI-as-client, MCP, UI scaffold, UI features)?~~
   **Answered** (owner,
   [PR #162 review](https://github.com/MadaraUchiha-314/the-loop/pull/162#discussion_r3718684765)):
   the breakdown shape is fine, but everything is delivered **in this single PR** —
   no sub-issue decomposition. `tasks.md` still structures the work as a DAG; the
   DAG just executes within one PR.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed.

- **2026-08-05 · @MadaraUchiha-314 ·
  [PR #162 review comment](https://github.com/MadaraUchiha-314/the-loop/pull/162#discussion_r3718668715)**
  (on §Open questions Q1): "Feel free to use any framework like FastAPI for this." —
  resolves Q1: the API layer may use a framework, chosen in the design phase; the
  non-functional dependency-budget requirement (optional extra, base install
  unchanged) still applies.
- **2026-08-05 · @MadaraUchiha-314 ·
  [PR #162 review comment](https://github.com/MadaraUchiha-314/the-loop/pull/162#discussion_r3718672701)**
  (on Q2): "Yes. CLI only uses the service :) it's the default and ONLY mode." —
  changes R2: no in-process execution path; R2.2/R2.3 rewritten accordingly.
- **2026-08-05 · @MadaraUchiha-314 ·
  [PR #162 review comment](https://github.com/MadaraUchiha-314/the-loop/pull/162#discussion_r3718677484)**
  (on Q3): "Feel free to use SOTA tooling like vite etc for this. Create a ui/
  folder where all the frontend assets will sit. All frontend code is TS - no
  exceptions." — adds R6.6.
- **2026-08-05 · @MadaraUchiha-314 ·
  [PR #162 review comment](https://github.com/MadaraUchiha-314/the-loop/pull/162#discussion_r3718678832)**
  (on Q4): "HTTP only. No stdio." — folded into R5.1: the MCP transport is HTTP.
- **2026-08-05 · @MadaraUchiha-314 ·
  [PR #162 review comment](https://github.com/MadaraUchiha-314/the-loop/pull/162#discussion_r3718684765)**
  (on Q5): "task breakdown looks ok. but i need all this done in a single PR." —
  delivery is this single PR; the program note updated, and the loop continues on
  PR #162 through design → tasks → implementation.
