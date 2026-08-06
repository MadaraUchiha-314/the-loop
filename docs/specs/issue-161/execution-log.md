---
type: execution-log
workItem: "issue-161"
phase: needs-review
status: in-progress
---

# Execution Log: control plane and API layer for the-loop

> Append-only log of progress for the user's visibility. Checked in alongside the spec
> at `docs/specs/issue-161/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-05 | _(pending — tier-4 program: this phase gate is human-reviewed on the spec PR)_ | Issue #161: re-architect into core / API layer / clients (CLI, MCP, UI). |
| design | 2026-08-05 | _(consolidated on PR #162 — single-PR delivery, owner decision)_ | Derived from locked requirements incl. the five answered forks. |
| tasks-breakdown | 2026-08-05 | _(consolidated on PR #162)_ | 15-task DAG, single-PR execution (owner decision). |
| implementation | 2026-08-05 |  | T1–T8, T10–T13 complete; T9 partial (check/events routed; pattern established). |
| needs-review | 2026-08-05 |  | Tier-4 human approval + named security sign-off on PR #162. |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| _(spec PR)_ `claude/github-issue-161-qto8z0` | Phase 1 requirements only | open |

## Progress entries

### 2026-08-05 — requirements drafted

- **Phase:** requirements-definition
- **Did:** read issue #161; surveyed the current CLI surface
  ([capability: cli](../../capabilities/cli.md), `cli/the_loop/` — ~18.5k lines,
  133 files) to ground the parity requirement (R2) in the real command list. Drafted
  `requirements.md`: three-layer architecture (R1), CLI feature parity with a
  preserved in-process mode (R2), durable contract-first API layer (R3), CLI-owned
  service/UI lifecycle (R4), MCP as an interface adapter (R5), statically-hostable
  control-plane UI (R6); threat-model-lite names the API-service-as-RCE boundary and
  binds loopback-by-default, fail-closed.
- **Judgement call — spec PR first, implementation in follow-ups:** this item
  re-layers the entire CLI and adds three new surfaces; `riskTier: 4` and
  `workflow.requireHumanReviewPerPhase: true` mean nothing downstream may be written
  against an unlocked requirements artifact. Unlike the recent bounded bugfixes
  (issue-154/156/159, where the whole loop fit one PR), drafting design/tasks or code
  now would bake in architecture decisions (API stack, CLI↔service relationship, UI
  toolchain, MCP transport) the owner hasn't weighed in on — those are recorded as
  open questions instead. Multi-PR delivery per work item is the sanctioned pattern
  (execution-log template: "a spec PR then an implementation PR").
- **Checkpoint/tests:** markdown lint on the new files (evidence on the PR).
- **Next:** owner reviews/locks `requirements.md` on the spec PR (answers to the five
  open questions welcome as review comments) → then `create-design` derives
  `design.md` from the locked requirements, including UI design artifacts under
  `design/`.
- **Blockers:** phase gate — human review of Phase 1 (tier 4).

### 2026-08-05 — phase-1 feedback folded in; design drafted

- **Phase:** requirements-definition → design
- **Did:** owner answered all five open questions on PR #162 (FastAPI sanctioned;
  CLI is service-only; `ui/` with Vite + TS-only; MCP HTTP-only; single-PR
  delivery) — folded into R2/R5/R6 + program note, appended to §Review comments,
  threads resolved. Drafted `design.md` (three layers, `[service]` extra,
  auto-start lifecycle, minimal JSON-RPC MCP endpoint, Vite+vanilla-TS UI,
  fail-closed security design), `design/control-plane.html` prototype, and
  decision-058.
- **Checkpoint/tests:** markdownlint clean; `the-loop check issue-161 --recompute
  --fail-on block` exit 0.
- **Next:** derive `tasks.md` (DAG, single-PR execution), then implement in
  dependency order (TDD per task).

### 2026-08-05 — implementation: core → API → clients

- **Phase:** tasks-breakdown → implementation → needs-review
- **Did (per DAG):** T1–T3 `the_loop.core` facade (23 tests); T4–T6 FastAPI
  `/api/v1` + authored OpenAPI contract + parity test + auth boundary (14
  tests); T7–T8 `service start|stop|status` (RunLock lifecycle) + stdlib
  client with auto-start and fail-closed `ServiceUnavailable`; T9 partial —
  `check` and `events` route through the service (routing seam,
  `THE_LOOP_SERVICE_LOCAL` loop guard, `--file` local escape); T10 `/mcp`
  JSON-RPC endpoint, 14 tools, exclusions enforced (6 tests); T11–T13 `ui/`
  Vite+TS frontend (typecheck+build green, live smoke screenshots in
  `design/`), `ui dev|build` command (3 tests), CI `ui` job. Schema gained the
  `service` block; docs pages for both commands + service options (parity
  gates green).
- **TDD note (honesty):** the facade/API tests were written with their
  modules per task and several passed first-run — thin adapters over
  already-tested modules leave little to go red. The negative/abuse-case
  tests (401s, exposure guard, fail-closed client, MCP exclusions) are the
  load-bearing coverage. Live-service integration tests exercise the real
  spawn/lock/token path.
- **Known limitations (deliberate, recorded):** T9's remaining commands
  (`sessions`, `graph` mutations, `scenarios`, `instructions`, `critic`,
  `poll`, `gh-webhook` entry points) still execute locally — the service-side
  surface for all of them is complete (REST + MCP), only their CLI transport
  switch remains; session/daemon control verbs run through the CLI's own verb
  as a transitional adapter (folding the dispatcher into core is follow-up);
  the CLI reads the local token file, so pointing it at a _remote_ service
  needs a token option (UI already handles this via its token field).
- **Checkpoint/tests:** `make check` (full CI parity) — evidence below.
- **Next:** owner review on PR #162 (tier-4 approval + named security
  sign-off); follow-up work item for the T9 remainder + dispatcher fold-in.

### 2026-08-05 — UI descoped on owner review

- **Phase:** needs-review (scope change during review)
- **Owner decision (PR #162):** "Let's remove the UI part from this PR. Just the
  services, CLI changes and the MCP."
- **Did:** removed the UI end to end — `ui/` (Vite + TS frontend), the
  `the-loop ui` command + its tests, the CI `ui` job, the `docs/cli/commands/ui`
  page, the UI design prototype + screenshots, and the CORS middleware +
  `service.ui.origins` config (no browser client → no CORS headers; the browser
  same-origin default is stricter than the pinned allowlist). R6 and R4.2 are
  recorded as **descoped to a follow-up work item** in `requirements.md`;
  T11–T13 marked descoped in `tasks.md`; design/capability docs updated. The
  `attention` core/API surface a UI would consume stays (also used over MCP).
- **Checkpoint/tests:** `make check` (full CI parity) after the removal —
  evidence below.
- **Next:** owner review of the reduced scope (services + CLI + MCP); tier-4
  named security sign-off still pending.

### 2026-08-05 — API contract relocated under docs/

- **Phase:** needs-review (review feedback)
- **Owner decision (PR #162 review):** "This should live inside `docs/` folder.
  since `specs` already exists within `docs`, let's call this `api-specs`."
- **Did:** moved `specs/openapi/the-loop.v1.yaml` →
  `docs/api-specs/openapi/the-loop.v1.yaml` and pointed this repo's
  `apiSpecs.rest.dir` at it (replacing the now-stale "apiSpecs: omitted — the-loop
  ships a CLI + docs, not a REST/GraphQL API" comment, which this work item made
  untrue). Updated the parity test, the capability doc, the `service` command page,
  decision-058 and the issue-161 spec artifacts.
- **Scoping call:** the **shipped default stays `specs/openapi`** for consuming
  projects — many have no `docs/` tree, so relocating the default would impose a
  docs layout on them. `apiSpecs.rest.dir` exists precisely for this per-project
  choice, so this repo overrides it. Raised on the PR in case the owner wants the
  default changed too.
- **Checkpoint/tests:** `make check` — full CI parity, green.
- **Next:** tier-4 named security sign-off; the T9 remainder decision.

### 2026-08-06 — no extras, official MCP SDK, and T9 completed

- **Phase:** needs-review (review feedback)
- **Owner decisions (PR #162 review), four in one comment thread:**
  1. _"No extras pls. It creates a nightmare when installing. All deps get
     installed when one installs the-loopy-one."_
  2. _"I hope we are using the official python SDK for MCP … Don't want to
     maintain custom implementation. Follow official SDKs."_
  3. On T9 being partial: _"Implement everything in this PR itself."_
  4. On the session/daemon control adapter: _"Do it in this PR itself."_
- **Did (1):** `fastapi`, `uvicorn`, `mcp` and `slack-sdk` became **required**
  dependencies; `[service]`, `[slack]` and `[config]` remain as empty no-ops so
  pinned install lines keep resolving. The MCP SDK requires Python 3.10+, so
  `requires-python` moved from `>=3.9` (EOL October 2025) — flagged BREAKING in
  its commit. The client's fail-closed message no longer names an install line,
  because an unreachable service is now only ever a lifecycle problem.
- **Did (2):** replaced the hand-rolled JSON-RPC endpoint with the official SDK.
  `api/mcp.py` is now the binding only — one thin function per tool, registered
  with `add_tool`, schemas derived from the annotations — and the SDK's
  DNS-rebinding protection is configured rather than reimplemented. The SDK app
  is mounted at the app **root** with its own path set to `/mcp`, so `/mcp`
  answers directly; mounting it _at_ `/mcp` left the real endpoint on `/mcp/` and
  a 307 on `/mcp`, which an MCP client that does not follow redirects on POST
  would fail to complete. `test_mcp_integration.py` now drives the real protocol
  (initialize → initialized → tools/list → tools/call).
- **Did (4):** the control verbs and daemon lifecycle moved **into** core.
  `core/sessions.py` owns register, close and start/pause/resume/stop end to end;
  it never prints, returning the lines it would have printed as tagged `messages`
  plus an `exitCode`, so the CLI is a renderer and all three surfaces produce the
  same words. `core/daemons.py` stops a daemon in-process (SIGTERM +
  `RunLock.wait_until_free`) and starts one via the new `the_loop.daemon_entry`
  module instead of shelling back into the-loop's own CLI verb. With no adapter
  left, `THE_LOOP_SERVICE_LOCAL` has no loop to prevent and is documented as what
  it now is: a test seam.
- **Did (3):** every remaining core-capability command routes — `sessions`
  (register/list/close/start/pause/resume/stop), `graph`
  (show/status/advance/complete/force/run), `scenarios`, `instructions`, `critic`
  (list/run), joining `check` and `events`. New API operations: `graphShow`
  (carrying the repo's spec root so `check --all` stops building a local
  runtime), `registerSession`, `closeSession`. `client/routing.py` gained
  `routed()` and `service_error()` so the routing decision and the HTTP-status →
  exit-code mapping are written once.
- **Judgment call, flagged:** `poll start` and `gh-webhook start` deliberately
  stay **foreground** process commands, because cron units and systemd
  `Type=simple` services depend on that; the same daemons start and stop detached
  through `/api/v1/daemons`. Likewise `sessions attach` (it execs tmux onto the
  caller's terminal) and `sessions reset` (recovery must work when nothing is
  running). These are local by nature, not leftovers.
- **Also:** on the owner's follow-up request, the `service` command page now
  documents installing and running the service and connecting an agent to `/mcp`
  from Claude Code, Claude Desktop and Cursor, with the tool table; the extras
  pages were rewritten now that there are none, and `service` was added to the
  docs sidebar (it had no entry).
- **Checkpoint/tests:** `make check` — lint, markdownlint, format, pyright,
  config validation and 1311 tests, green. Two new integration tests drive the
  **real** CLI against a **live** service: every routed command end to end, and
  fail-closed (exit 2, naming `the-loop service start`) with auto-start off.
- **Next:** tier-4 named security sign-off; whether the shipped `apiSpecs`
  default should move too (open question on the PR).

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self (spec re-read against issue #161 + capability docs) | harness | zero (converged) | — |
| 2 | self (implementation re-read: client/config resolution, error mapping, subprocess spawns) | harness | new finding — `connect()` with no config ignored the operator's CLI config (custom `service.port` unread); fixed with `_resolved()` | commit on PR #162 |
| 3 | self (security-focused: CORS, token handling, argv spawns, MCP exclusions, audit records) | harness | zero new (remote-token limitation recorded, not a defect) | — |
| 4 | critic | — | **unavailable** — `reviews.critics` is empty in this repo's config; does not count toward `criticReviewCount` | — |
| 5 | security (gate) | security-review skill (adversarial sub-agent) | one HIGH (UI token exfil via `?api=`) — first fixed by origin-pinning, then **resolved at root** by removing in-app auth (decision-059, owner); `esc()` quote-hardening kept | see Security review section |
| 6 | owner direction (PR #162) | @MadaraUchiha-314 | remove in-app authentication — the gateway owns auth (decision-059); implemented, 1310 tests green | [comment](https://github.com/MadaraUchiha-314/the-loop/pull/162#issuecomment-5194359297) |
| 7 | owner direction (PR #162) | @MadaraUchiha-314 | remove the UI from this PR — services, CLI and MCP only; R6/R4.2 descoped to a follow-up work item, frontend + CORS removed | PR #162 |
| 8 | owner review (PR #162) | @MadaraUchiha-314 | move the API contract under `docs/` as `api-specs`; done via a repo-local `apiSpecs.rest.dir` override, shipped default untouched | PR #162 |
| 9 | owner direction (PR #162) | @MadaraUchiha-314 | four directives: no extras; official MCP SDK; finish T9; fold the control adapter into core. All four implemented, 1311 tests green | PR #162 |
| 10 | owner request (PR #162) | @MadaraUchiha-314 | document installing/running the service and wiring `/mcp` into Claude and Cursor; `docs/cli/commands/service.md` rewritten and added to the sidebar | PR #162 |

## Security review (gate)

> Runs at ready-to-ship (implementation PRs). This spec PR carries no code; the
> threat model itself is in `requirements.md` § Security considerations. Tier 4 ⇒ a
> named human security sign-off will be required on the implementation.

- **Mechanism:** built-in `security-review` skill (`security.review.mechanism:
  auto`), run against the branch diff by an adversarial sub-agent.
- **Outcome (first pass, on the token design):** one HIGH — the UI's `apiBase()`
  trusted and persisted the `?api=` query param, then attached the bearer token
  to that origin (one-click token-exfiltration via a poisoned same-origin link).
  Fixed at the time by pinning the token to allowlisted origins and hardening
  `esc()` to escape quotes.
- **Superseded by decision-059 (owner):** the owner then directed **removing
  in-app authentication entirely** — the deploying gateway owns auth. The bearer
  token is gone end to end (no minting, no `Authorization` check, no token in the
  client or UI), which **resolves the HIGH at its root**: there is no credential
  to exfiltrate. The `esc()` quote-hardening is kept (defense-in-depth for
  rendering API data). The service's own boundary is now **network scoping** —
  loopback-by-default plus the `service.exposed` guard — with the gateway
  responsible for authentication on any exposed deployment. CORS pinning, input
  validation (ref parser, repo-path directory check), the argv-no-shell critic
  runner, and the MCP exclusions (`sessions reset`, `graph force`) are unchanged.
- **Residual risk (recorded):** an operator who sets `service.exposed: true`
  **without** a fronting gateway would publish an unauthenticated RCE-equivalent
  endpoint. The exposure guard makes that a deliberate act and the docs state it
  plainly; it is the gateway's job by design (decision-059).
- **Human sign-off:** required at tier 4 (`security.review.humanSignOffMinTier:
  4`) — **pending** the owner's named sign-off on PR #162; the posture to sign
  off is now "network boundary + gateway", not a token scheme.

## Final validation evidence

Pending — recorded when implementation lands.
