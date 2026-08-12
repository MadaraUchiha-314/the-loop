---
type: execution-log
workItem: issue-211
phase: needs-review
status: in-progress
---

# Execution Log: configurable CORS so the hosted dashboard can reach the service

> Append-only log for issue-211. Ticket:
> [#211](https://github.com/MadaraUchiha-314/the-loop/issues/211).

## How this session ran the loop

One cloud session, one pass, no human at the other end. Two consequences a reviewer
should hold while reading:

1. **`phase-selection` was not run as a gate.** The loop's rule is that a human ticks the
   phases; there was nobody to tick, and the session was started by the ticket itself.
   Phases assumed: the full spec chain, verification, self-review. `brainstorming` and the
   opt-in `design-critic-review` were not taken — the ticket states the problem and the
   remedy precisely enough that there was nothing to brainstorm, and no second model was
   available to critic the design.
2. **The chain was authored before the code, but approved by nobody.** The artifacts are a
   proposal to ratify, not a locked chain. `status: draft` on all four says so.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-12 | — | Not run as a gate; see above |
| requirements-definition | 2026-08-12 | | [`requirements.md`](requirements.md) — 4 requirements, 3 NFRs, 6 abuse cases. Risk tier **4**: `autonomy.inferFromChange` matches `sensitivePaths: **/*schema*` (the CLI config schema gains a block) and the change widens who may read the control plane, so the gate is `human-approves-pr` **and** a named human security sign-off is required (`security.review.humanSignOffMinTier: 4`) |
| design | 2026-08-12 | | [`design.md`](design.md) — one config resolver, one middleware, one start-up guard; the three deliberate absences (no `enabled` key, no origin regex, no new network boundary) |
| test-planning | 2026-08-12 | | [`testing-plan.md`](testing-plan.md) — 10 rows in scope, 5 `n/a` with reasons, and a § Coverage gaps |
| tasks-breakdown | 2026-08-12 | | [`tasks.md`](tasks.md) — 10 tasks, three independent roots off the schema |
| implementation | 2026-08-12 | | Built. Tasks 1–9 complete |
| verification | 2026-08-12 | | Testing plan executed: every activity but T11 (needs a human at a browser). 1819 tests pass; lint, format, types, markdown and schema validation clean |
| needs-review | 2026-08-12 | | Handed to the PR |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| `claude/github-issue-211-bvoxlt` | the whole work item | open, awaiting human approval + security sign-off |

## Progress entries

### 2026-08-12 — the shape of the change

Read the service's three seams before writing anything: `api/config.py` (how `service` is
resolved today), `api/serve.py` (the exposure guard, and where a refusal belongs), and
`api/mcp.py` (whether an app-wide middleware could hand a browser the MCP endpoint). The
third one decided the scope: the MCP transport keeps its own DNS-rebinding origin
allowlist, pinned to loopback, so a CORS header cannot make `/mcp` drivable from a page —
which is why the middleware could stay app-wide instead of being scoped to a sub-app.

Three things the research changed:

- **`allow_private_network` is not optional for the flagship case.** A public HTTPS page
  reaching `http://127.0.0.1` is exactly what Chromium gates behind a private-network
  preflight, so shipping CORS without answering it would have left the ticket's own
  scenario broken in the most common browser. Starlette supports it natively; the kwarg is
  passed only when the installed version accepts it, because the package floor
  (`fastapi>=0.110`) resolves to versions that predate it.
- **The middleware must be added *last*.** Starlette wraps the most recently added
  middleware outermost, so adding CORS after `_audit` is what makes a preflight
  short-circuit before the audit trail — and, more to the point, before
  `POST /api/v1/sessions/control`'s route. A test asserts nothing is emitted.
- **The `enabled` key was dropped.** An empty `allowOrigins` is the off switch and the same
  condition the code branches on, so there is no boolean that can disagree with the list it
  guards.

### 2026-08-12 — self-review findings

Both found by re-reading the diff, both fixed before the PR:

- `_as_list` raised `TypeError` on a non-sequence scalar (`allowOrigins: 8787`). The CLI
  config is loaded **without** schema validation, so that would have escaped `serve`'s
  `except ValueError` as a traceback. It now resolves to one origin that matches nothing,
  with a test.
- An origin pasted as a **URL** (`https://…/the-loop/ui/`) silently matches no request.
  `_install_cors` now warns once, naming the entries, rather than letting it read as "CORS
  is broken".

### 2026-08-12 — a pre-existing gap, closed in passing

`docs/config/cli/service-options.md` existed since issue-161 but was in neither the
VitePress sidebar nor the "Options by area" table, so the page an operator now needs was
unreachable by navigation. Both fixed here rather than filed: this work item is the reason
somebody would go looking.

## Documentation

| Doc | Change |
|-----|--------|
| [`docs/config/cli/service-options.md`](../../config/cli/service-options.md) | New § Cross-origin access: the five keys with Type/Default, and a warning block stating what the default admits |
| [`docs/config/cli/index.md`](../../config/cli/index.md) · `docs/.vitepress/config.mts` | The service-options page added to the "Options by area" table and the sidebar (it was in neither) |
| [`docs/cli/commands/service.md`](../../cli/commands/service.md) | New § The web dashboard, and CORS — why the hosted page now works with no gateway, and that this is a read permission, not a network one |
| [`docs/capabilities/control-plane.md`](../../capabilities/control-plane.md) | Current behaviour restated (the "no CORS headers are sent" bullet was made false by this change), plus the middleware-ordering and MCP-origin invariants, and an issue-211 history row |
| [`docs/decisions/decision-077.md`](../../decisions/decision-077.md) | New — the default-origin call, its cost, and the four alternatives |
| [`ui/README.md`](https://github.com/MadaraUchiha-314/the-loop/blob/main/ui/README.md) | § Reaching a service from a hosted page rewritten: same-machine needs nothing now; the tunnel is for another machine |
| `skills/the-loop/templates/cli-config.yaml` | The `service` block, with the cors sub-block and its warning, so `/the-loop:init` scaffolds it |
| `.the-loop/cli-config.yaml` | The same block, dogfooded here |

The skill and its `reference/` are untouched: this changes a service's configuration, not
how the loop is run.

## Capability docs

[`docs/capabilities/control-plane.md`](../../capabilities/control-plane.md) — updated in
this PR (see the table above). No other capability doc describes the service's network
posture.

## Verification results

In [`testing-plan.md`](testing-plan.md) § Verification results, with evidence under
[`evidence/`](evidence/). Summary: everything but T11 executed and passing; T11 (the
hosted page against a real service, in a real browser) needs a human and is the one thing
to do before merge.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (this session) | new findings — the `TypeError` escape and the pasted-URL silence, both above, both fixed with tests | [`config.py`](../../../cli/the_loop/api/config.py), [`app.py`](../../../cli/the_loop/api/app.py) |
| 2 | self | the-loop (this session) | new finding — the preflight test proved the *headers* but not the claim that no operation runs; it now also asserts the event log stays empty, which is what actually pins the middleware ordering | [`test_api_cors_integration.py`](../../../cli/tests/test_api_cors_integration.py) |
| 3 | self | the-loop (this session) | new finding — the MCP negative test passed on the `Host` check, not the `Origin` check, so it would have kept passing if the origin allowlist were widened. Pinned to a 403 with an accepted `Host` | [`test_api_cors_integration.py`](../../../cli/tests/test_api_cors_integration.py) |
| 4 | critic | — | **not run.** `reviews.critics` is empty in this repo's harness config and no second harness was available to this session | |
| 5 | security | — | **not run.** Risk tier 4 requires a **named human** security sign-off; this session cannot sign off on its own widening of a read boundary. The material for it is [`requirements.md`](requirements.md) § Security considerations (6 abuse cases), [`design.md`](design.md) § Security design (each one's mechanism and its negative test) and [`decision-077`](../../decisions/decision-077.md) | |
