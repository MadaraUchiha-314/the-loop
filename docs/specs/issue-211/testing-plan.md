---
type: testing-plan
phase: test-planning
workItem: issue-211
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: configurable CORS so the hosted dashboard can reach the service

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md), before
> [`tasks.md`](tasks.md). Authored at `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `cors_config()` resolution: defaults with no block, per-key override, coercion, and the refused wildcard+credentials combination | `uv run --project cli python -m pytest -q cli/tests/test_api_cors.py` |
| T2 | Integration (scenario) | yes | The app as assembled: an allowed origin is echoed, an unlisted one is not, a preflight is answered without touching the operation, an empty list installs no middleware | `uv run --project cli python -m pytest -q cli/tests/test_api_cors_integration.py` |
| T3 | Contract (OpenAPI) | yes | The served surface is unchanged — preflight handling adds no path, method or operationId (NFR3) | `uv run --project cli python -m pytest -q cli/tests/test_api_contract_parity.py` |
| T4 | End-to-end | n/a — an e2e run means a real browser against a real `service start`; the browser half is T11, and nothing between the fetch and the middleware is ours to integrate | | |
| T5 | UI / visual | n/a — the dashboard's changes are three strings of copy; no component, layout or token moves, so there is no visual state to capture | | |
| T6 | Snapshot | n/a — no serialized artifact is produced by this change | | |
| T7 | Performance / load | n/a — one middleware on an already-async stack, with Starlette's 600s preflight cache; no measurable budget is at stake | | |
| T8 | Security / abuse case | yes | One negative test per mechanism in `design.md` §Security design: unlisted origin, suffix-lookalike origin, wildcard+credentials refusal at both layers, private-network decline, `/mcp` origin allowlist unchanged | `uv run --project cli python -m pytest -q cli/tests/test_api_cors.py cli/tests/test_api_cors_integration.py` |
| T9 | Accessibility | n/a — no interactive surface changes | | |
| T10 | Migration / upgrade | yes | An existing config without a `service.cors` block still loads, and `CURRENT_CONFIG_VERSION` does not move — nothing was removed or renamed | `uv run --project cli python -m pytest -q cli/tests/test_cli_config.py cli/tests/test_migrations.py` |
| T11 | Manual exploratory | yes — **the only test that proves the ticket** | The published page at `https://madarauchiha-314.github.io/the-loop/ui/` loading real data from a locally running `the-loop service start` | a human, a browser, a workstation |
| T12 | Docs parity | yes | Every new schema leaf is documented with Type and Default (R4.1) | `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py` |
| T13 | Schema validation | yes | The checked-in `.the-loop/cli-config.yaml` still validates against the amended schema | `make validate` |
| T14 | Lint / format / types | yes | Repo gates, CI parity | `make lint format-check typecheck` |
| T15 | UI unit | yes | The retargeted cross-origin advice assertion in `ui/src/api/client.test.ts` | `bun run test` in `ui/` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R2.1, R2.2, R2.3, R3.4 | no `service.cors` block → the five documented defaults |
| T1 | R3.1 | `"*"` + `allowCredentials: true` → `ValueError` naming both keys |
| T1 | R1.4 | a scalar `allowOrigins` is coerced to a one-entry list, not iterated per character |
| T2 | R1.1 | `Scenario: an allowed origin reads the control plane` |
| T2 | R1.3, R1.4 | `Scenario: an unlisted origin gets no allow-origin header` |
| T2 | R1.2 | `Scenario: a preflight is answered without running the operation` |
| T2 | R2.3 | `Scenario: a private-network preflight is answered for an allowed origin` |
| T2 | R2.4 | `Scenario: an empty origin list leaves the service exactly as it was` |
| T2 | R3.2 | `Scenario: an invalid CORS configuration stops the service before it binds` |
| T8 | abuse 5 | `Scenario: the MCP transport still refuses a foreign origin` |
| T3 | NFR3 | the authored contract still equals the served schema |
| T10 | R2.4 | a pre-issue-211 config loads unchanged |
| T11 | R1.1, R2.1, R2.3 | the hosted dashboard renders live work items from a loopback service |
| T12 | R4.1 | P4/P5 over `service.cors.*` |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none for T1–T10 and T12–T15 — `fastapi.testclient.TestClient`
  drives the app in-process. T11 needs `uv run the-loop service start` on the reviewer's
  own workstation.
- **Fixtures & data:** none. Config dictionaries are built inline per test; `state.root`
  points at `tmp_path`, as in `test_api_auth.py`.
- **Credentials:** none — this work item reads, writes and logs no secret.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8 | pytest run of the two new files, with counts | `unit-and-integration.md` |
| T3, T10, T12, T13, T14 | full-suite run plus `make validate` / lint / typecheck output | `repo-gates.md` |
| T15 | `bun run test` output, or the reason it could not run | `ui.md` |
| T11 | screenshot of the hosted page showing live data, and the browser network panel's response headers — **by a human, at review** | `manual-browser.md` |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_api_cors.py`
- [x] T2, T8 — `uv run --project cli python -m pytest -q cli/tests/test_api_cors_integration.py`
- [x] T3, T10, T12 — `uv run --project cli python -m pytest -q cli`
- [x] T13 — `make validate`
- [x] T14 — `make lint format-check typecheck`
- [x] T15 — `bun run test` in `ui/`
- [ ] T11 — hosted page against a local service, by a human

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `pytest cli/tests/test_api_cors.py` | pass — 8 cases | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T2, T8 | `pytest cli/tests/test_api_cors_integration.py` | pass — 11 cases, 6 of them negative | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| — | headers captured from the assembled app on the shipped defaults | pass — allowed origin echoed by name with `Vary: Origin`, private-network header present, disallowed origin gets none | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T3, T10, T12 | `pytest -q cli` | pass — 1819 passed, 1 skipped; contract parity, config load and docs parity all unchanged | [`repo-gates.md`](evidence/repo-gates.md) |
| T13 | `uv run python scripts/validate_config.py` | pass — 7 files valid, both CLI configs carrying the new block | [`repo-gates.md`](evidence/repo-gates.md) |
| T14 | `ruff check` · `ruff format --check` · `pyright` · `markdownlint-cli2` | pass — 0 findings each | [`repo-gates.md`](evidence/repo-gates.md) |
| T15 | `bun run test` · `bun run lint` · `bun run typecheck` in `ui/` | pass — 50 tests, lint and types clean | [`ui.md`](evidence/ui.md) |
| T11 | hosted page against a local service | **not executed** | — |

**Not executed:** T11 — the only activity that proves the ticket end to end needs a
browser, a workstation running `the-loop service start`, and the page at
`https://madarauchiha-314.github.io/the-loop/ui/` **as published from this branch's
merge**. This session has none of the three. Everything below the browser is pinned: the
exact headers a browser would receive are captured in the evidence, and the private-network
header — the part most likely to differ between browsers — is asserted rather than assumed.
What remains unproven is the browser's own judgement of them, and Safari in particular is
known to treat `http://127.0.0.1` from an HTTPS page more strictly than Chromium does.
Escalated to the reviewer as the one manual step before merge, and named in the PR
briefing.

## Coverage gaps

- **No test drives a real `uvicorn` process.** Every assertion is `TestClient` in-process.
  The middleware is Starlette's, and the ASGI stack is the same one uvicorn serves, so the
  risk is bounded to the process boundary itself — which the existing
  `test_service_lifecycle_integration.py` already covers for start/stop.
- **`allow_private_network` on an older Starlette is not exercised.** The compatibility
  branch in `_install_cors` is reachable only with a Starlette that predates the parameter;
  this repo's lockfile pins a newer one, and installing an old one inside a test would pin
  a dependency's history rather than our behaviour.

## Review comments

<!-- Populated at review. -->
