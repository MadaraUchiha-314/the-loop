---
type: execution-log
workItem: issue-212
phase: implementation
status: in-progress
---

# Execution Log: a Python SDK that embeds the-loop into somebody else's service

> Append-only log for issue-212. Ticket:
> [#212](https://github.com/MadaraUchiha-314/the-loop/issues/212).

## How this session ran the loop

One cloud session, one pass — the posture of issue-208 through issue-228, with the same two
consequences a reviewer should hold:

1. **`phase-selection` was not run as a gate.** The session was started from the ticket;
   there was nobody to tick the checklist. Phases assumed: full spec chain, implementation,
   verification, self-review. `brainstorming` not taken (the ticket enumerates its own
   questions and the owner's follow-up comment — *"With the latest changes that have been
   merged, we should be in a good position to make this change"* — closes the "is it time"
   question). The opt-in `design-critic-review` not taken: no second model is available to
   this session.
2. **The chain was authored before the code, but approved by nobody.** All four artifacts are
   `status: draft` — a proposal to ratify with the PR. Risk tier **3**
   (`requirements.md` §Risk tier) ⇒ human approves the PR; no separate named security
   sign-off.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-15 | — | Not run as a gate; see above |
| requirements-definition | 2026-08-15 | | [`requirements.md`](requirements.md) — 7 requirements, 5 NFRs, security §, risk tier 3 |
| design | 2026-08-15 | | [`design.md`](design.md) — 5 design points, decision-085 |
| test-planning | 2026-08-15 | | [`testing-plan.md`](testing-plan.md) — 14 rows, 6 `n/a` with reasons |
| tasks-breakdown | 2026-08-15 | | [`tasks.md`](tasks.md) — 16 tasks |
| implementation | 2026-08-15 | | 16 tasks; 5 new modules, 5 new test files, 2 refactored modules, 15 documents |
| verification | 2026-08-15 | | Testing plan executed in full; see [`testing-plan.md`](testing-plan.md) §Verification results and [`evidence/`](evidence/) |
| needs-review | 2026-08-15 | | Handed to the PR |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| `claude/github-issue-212-n81fy7` | the whole work item | open, awaiting human approval |

## Progress entries

### 2026-08-15 — orientation

Read the ticket and its one comment, `CLAUDE.md`, the skill, the harness config, and the
whole current control plane: `api/app.py` (629 lines, 29 routes as closures), `api/serve.py`,
`api/mcp.py`, `api/ingress.py`, `api/config.py`, the eight `core/` modules, `cli_config.py`,
the harness adapters and `runner.check_dependencies`. Three findings shaped the design:

- **The capability layering is already right.** decision-058's `core` facade is transport-free
  and importable with no HTTP context. The SDK needed to add no capability — only a seam.
- **`create_app` is an application, not a component.** Its routes are closures in its body,
  its per-request behaviour is middleware, and its error mapping is app-level handlers. All
  three are properties of an *app object*, which is exactly what an embedder does not want a
  second of — hence D1 and D2.
- **A mounted sub-app's lifespan never runs.** Starlette does not run it, so today's
  "mount `create_app`" workaround silently produces a dead MCP session manager and no hosted
  ingresses. That failure is invisible until the first `/mcp` POST, which is why `mount()`
  wraps the host lifespan by default (D3).

### 2026-08-15 — building it

Order: the refactor first (T1–T4), with the existing suite as the gate that it changed
nothing; then the SDK (T5–T8); then tests, docs and the vendor-SDK analysis. The checkpoint
after T4 held on the first attempt — **2041 passed, 1 skipped, no test adapted** — before a
line of `the_loop/sdk/` existed.

Four things came out of doing it rather than planning it:

1. **`ConfigHolder` had to leave `api/`.** The design put it in `api/routes.py` beside the
   router that drives it, which would have made NFR2 unsatisfiable: `TheLoop.__init__` builds
   a holder, so constructing an SDK instance would have imported FastAPI. It moved to
   `the_loop/cli_config.py` instead, which is a better home anyway — it *is* the CLI config
   kept level with the file, and `reload.py` is stdlib-only, so nothing circular follows.
   Verified with a fresh-interpreter assertion (`test_importing_the_sdk_does_not_import_fastapi_or_mcp`).
2. **`install_hint` came out of the environment table.** The design's data model carried one.
   Two places already own install hints (`runner._INSTALL_HINTS`, `poller.github._GH_INSTALL_HINT`),
   so a third would have been a copy to drift; the minimalism ladder says the docs page owns
   that prose. The report keeps `capability` and `configKey`, which is what R5.2 actually asks
   for.
3. **`app.routes` does not list included routes on this FastAPI.** The abuse-case test first
   walked `app.routes` looking for the mounted operations and found an `_IncludedRouter`
   wrapper instead — it silently checked *nothing*, and passed. Rewritten to drive off the
   host application's own `/openapi.json`, which is both correct and the question a caller
   would ask: "what did this mount publish, and is any of it open?" A test that passes by
   checking nothing is the failure mode worth recording here.
4. **`ttyd` joined the requirement table.** The design listed five binaries; `routing.webTerminal`
   makes six. Found while writing the table, not while writing the design.

### 2026-08-15 — verifying it

The plan ran end to end (results table in [`testing-plan.md`](testing-plan.md)). Two rows are
worth a note:

- **T13 (manual)** ran the docs' own quickstart under a real `uvicorn` rather than
  `TestClient`, because the property under test is that *the documentation is followable* —
  and because `StreamableHTTP session manager started` in the boot log is the only direct
  proof that `mount()`'s lifespan wrapping did what D3 claims.
- **T14** surfaced one pyright error (reading `.operation_id` off `BaseRoute` in the new
  parity assertion), fixed by narrowing rather than suppressing.

Final: **2098 passed, 1 skipped**; ruff, pyright, markdownlint (671 files) and the config
validator all clean.

### 2026-08-15 — self-review

Three rounds over the full diff, findings fixed in place:

1. **Round 1 — the stale SHALL clause.** `docs/capabilities/control-plane.md` still said "the
   CORS middleware SHALL sit outside the audit middleware", and there is no audit middleware
   any more. Rewritten to state what is now true, plus the new router/route-class clause — a
   capability doc is the source of truth for *current* behaviour, so a clause describing a
   mechanism that was deleted is a defect, not a cosmetic lag.
2. **Round 2 — scope discipline on the docs nav.** The capabilities sidebar is missing entries
   for `control-plane` and `process-graph`. Adding them while adding `sdk` was tempting and
   wrong: they are pre-existing gaps, not this work item's. Only `sdk` was added.
3. **Round 3 — the follow-up issue numbers.** The vendor-SDK report was written with
   placeholder numbers before the issues existed; corrected to the real ones (#232–#234) after
   filing, and cross-checked in both directions.

No round produced a repeated finding, so nothing escalated. **No critic round ran**: no second
model is available to this session (`reviews.critics` is empty in this repo's config), which is
a gap a human reviewer should weigh rather than assume covered.

## Capability docs

- [`docs/capabilities/sdk.md`](../../capabilities/sdk.md) — **new capability**, indexed in
  `capabilities.md`: the SDK's whole behaviour as SHALL clauses (construction and strict
  config, the eight namespaces, the one-router guarantee, the route class, the two-touch
  mount rule, lifespan composition, the MCP prefix rule, the environment contract, and what
  is deliberately absent).
- [`docs/capabilities/control-plane.md`](../../capabilities/control-plane.md) — the CORS
  clause corrected (no audit middleware exists; CORS is the standalone *application's*), a
  new clause for the one-router/route-class arrangement, and an issue-212 history row.

## Documentation

- `docs/sdk/` — **new section**: `index.md` (what it is, when to use it instead of the
  standalone service, the two surfaces, configuration), `embedding.md` (the authorization
  warning first, then prefixes, middleware, CORS, lifespan, MCP, hosted ingresses, the two
  operations that mean something different when embedded, and a pre-ship checklist),
  `environment.md` (the binary contract, a Dockerfile, and the credentials a preflight cannot
  check), `reference.md` (every public symbol and every namespace method).
- `docs/.vitepress/config.mts` — an `/sdk/` sidebar, a top-level **SDK** nav entry, the SDK
  reference under Reference, `capabilities/sdk` in the capabilities list, and the vendor-SDK
  report under Reports.
- `README.md` — a **The SDK** section after **The CLI**; `cli/README.md` (the PyPI front
  page) — an **Or embed it** section and a docs-table row; `docs/index.md` — a hero action
  and a feature card; `docs/cli/service.md` — a tip pointing an operator who already runs a
  Python service at the SDK.
- `docs/reports/vendor-sdk-analysis.md` + its index and sidebar entries — the R7 analysis.
- `docs/decisions/decision-085.md` + the log row.
