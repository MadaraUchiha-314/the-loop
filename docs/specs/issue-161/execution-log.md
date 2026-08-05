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

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self (spec re-read against issue #161 + capability docs) | harness | zero (converged) | — |
| 2 | self (implementation re-read: client/config resolution, error mapping, subprocess spawns) | harness | new finding — `connect()` with no config ignored the operator's CLI config (custom `service.port` unread); fixed with `_resolved()` | commit on PR #162 |
| 3 | self (security-focused: CORS, token handling, argv spawns, MCP exclusions, audit records) | harness | zero new (remote-token limitation recorded, not a defect) | — |
| 4 | critic | — | **unavailable** — `reviews.critics` is empty in this repo's config; does not count toward `criticReviewCount` | — |
| 5 | security (gate) | security-review skill (adversarial sub-agent) | one HIGH (UI token exfil via `?api=`) — first fixed by origin-pinning, then **resolved at root** by removing in-app auth (decision-059, owner); `esc()` quote-hardening kept | see Security review section |
| 6 | owner direction (PR #162) | @MadaraUchiha-314 | remove in-app authentication — the gateway owns auth (decision-059); implemented, 1310 tests green | [comment](https://github.com/MadaraUchiha-314/the-loop/pull/162#issuecomment-5194359297) |

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
