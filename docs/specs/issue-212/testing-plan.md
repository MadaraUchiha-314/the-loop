---
type: testing-plan
phase: test-planning
workItem: issue-212
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: a Python SDK that embeds the-loop into somebody else's service

> Derived from the approved `requirements.md` and `design.md`, **before** `tasks.md` — each
> task's `_Test:_` names a row of the matrix below. Authored at `test-planning` and completed
> at `verification`. See `reference/testing.md`.
>
> **This file is executable content.** Review the commands like code. No credentials appear
> here, by value or by reference — none are needed (see §Verification environment).

## Test matrix

The work item is a library seam over an existing, well-tested core, so the proof splits
three ways: **the refactor changed nothing** (the existing suite, unchanged), **the seam
behaves when embedded** (new integration tests against a host application), and **the
contract cannot drift** (parity gates). Everything runs offline, in-process, on this
repository.

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `TheLoop` construction (path / dict / both / missing / unparseable), the `mount()` report, the environment table's per-config `required` predicates, `ok` arithmetic | `uv run --project cli pytest tests/test_sdk_client.py tests/test_sdk_environment.py` |
| T2 | Integration (scenario) | yes | the SDK mounted in a *host* FastAPI app: prefix routing, host middleware, injected dependencies, lifespan composition (both orders), MCP under a prefix, error translation without host handlers | `uv run --project cli pytest tests/test_sdk_embedding_integration.py` |
| T3 | Contract (OpenAPI) | yes | the router's operations == the standalone app's == the authored `docs/api-specs/openapi/the-loop.v1.yaml` | `uv run --project cli pytest tests/test_api_contract_parity.py` |
| T4 | Regression (existing suite) | yes | D1/D2 moved code between modules and changed no behaviour: every pre-existing API, core, graph and CLI test passes **unchanged** | `uv run --project cli pytest` |
| T5 | Docs parity | yes | every public SDK symbol is documented; every binary in the requirement table appears in `docs/sdk/environment.md`; every namespace method resolves to a real `core` callable | `uv run --project cli pytest tests/test_sdk_docs_parity.py` |
| T6 | End-to-end | n/a — an e2e run would need a live `gh`, a GitHub repository and a harness binary spawning real sessions. The seam under test terminates at `the_loop.core`, which the existing suite already exercises against fixtures; adding a networked e2e here would test issue-161's code, not this work item's. | | |
| T7 | UI / visual | n/a — no rendered output. This work item ships a library surface and documentation; `design.uiArtifacts` does not apply (`design.md` §UI/UX design). | | |
| T8 | Snapshot | n/a — the one artifact worth pinning is the OpenAPI surface, and T3 pins it against an authored contract, which is stronger than a snapshot (a snapshot ratifies whatever the code did; the contract is reviewed). | | |
| T9 | Performance / load | n/a — the SDK adds no work per request beyond what `create_app` already did; the route class replaces a middleware pass with an equivalent per-route pass over the same `sha256` config check. No latency claim is made, so none is measured. | | |
| T10 | Security / abuse case | yes | one negative test per abuse case in `requirements.md` §Security considerations that this code can be made to fail: dependency-gated routes cannot be bypassed by path, the SDK installs nothing on the host app, `check_environment` executes nothing, `prefix=""` with MCP is refused | `uv run --project cli pytest tests/test_sdk_security_integration.py` |
| T11 | Accessibility | n/a — no user interface. | | |
| T12 | Migration / upgrade | n/a — nothing is removed, renamed or moved in the CLI config, the on-disk state or the CLI surface. `the_loop.api.app.create_app` keeps its signature and behaviour; the change is additive to the package. | | |
| T13 | Manual exploratory | yes | one runnable embedding sample — the docs' own quickstart, pasted into a scratch file and served with uvicorn — proving the documentation is followable end to end (R6.2) | manual, output captured as evidence |
| T14 | Lint / type / format | yes | the repository's own gates, on the same commands CI runs | `make lint typecheck` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R4.1, R4.2, R4.6 | `TheLoop(config_path=…)` reads that file; no argument resolves by the standard order; `config=` uses the document |
| T1 | R4.5 | a missing path raises `FileNotFoundError` naming it; an unparseable one raises `ValueError` naming it |
| T1 | R1.5, NFR2 | importing `the_loop.sdk` leaves `fastapi` and `mcp` unimported until the HTTP seam is asked for |
| T1 | R5.2, R5.3, R5.4 | the report's shape; `required` follows `routing.defaultHarness` and `routing.enabled`; optional-missing stays ok; nothing is executed |
| T1 | R2.4, R3.6 | the `mount()` report names the prefix, operation count, MCP path and lifespan mode; `host_ingresses=False` is reflected |
| T2 | R2.1, R2.2 | `Scenario: a host application serves the-loop's operations under its own prefix` |
| T2 | R2.3 | `Scenario: a core LookupError becomes a 404 in a host app that registered no handlers` |
| T2 | R3.1 | `Scenario: the host application's middleware sees every the-loop request` |
| T2 | R3.2 | `Scenario: an injected dependency gates every the-loop operation` |
| T2 | R2.5, R3.4 | `Scenario: the MCP endpoint answers under a prefix with the host's lifespan still running` |
| T2 | R2.6 | `Scenario: mounting MCP without composing the lifespan refuses instead of serving` |
| T2 | R4.3 | `Scenario: a config edited on disk is live on the next embedded request` |
| T2 | NFR4 | `Scenario: an embedded operation lands in the event log as api.request` |
| T3 | R2.1, R2.7 | the three operation sets are equal |
| T4 | R2.7, and the whole refactor | the pre-existing suite passes unchanged |
| T5 | R6.3, R6.4 | public symbols ↔ docs; environment table ↔ environment page; namespace methods ↔ `core` |
| T10 | abuse case 2 | `Scenario: a rejecting dependency cannot be bypassed by choosing a the-loop path` |
| T10 | R3.3, R3.5 | `Scenario: mounting adds no middleware, no exception handlers and no CORS to the host app` |
| T10 | abuse case 5 | `Scenario: the environment preflight resolves binaries without executing them` |
| T10 | design D3 | `Scenario: an empty prefix with MCP enabled is refused rather than shadowing host routes` |
| T13 | R6.2 | the documented quickstart runs as written |
| T14 | — | repository gates |

## Verification environment

- **Repositories:** this repository only. Every test runs against `cli/` with the repo's own
  `docs/` tree present (the parity rows read it).
- **Services / containers:** none. FastAPI's `TestClient` hosts the applications under test
  in-process; T13 runs one local `uvicorn` on a loopback port and stops it.
- **Fixtures & data:** `tmp_path`-scoped CLI configs and state roots, in the style
  `tests/test_api_routers_integration.py` already uses. No network, no `gh`, no harness
  binary: the environment row's tests assert on *resolution*, using a `PATH` the test
  controls.
- **Credentials:** none — not by value and not by reference. Nothing under test authenticates
  to anything.
- **Bring-up:** `uv sync` · **Tear-down:** none (no process, container or state outlives a
  test).
- **If bring-up fails:** record it under Verification results, leave the dependent activities
  unticked, and escalate — the gate is not passed on an environment that never came up.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T10 | run output per file: counts, duration, the Gherkin scenario titles | `tests.md` |
| T3, T4, T5 | full-suite run: counts, duration, and the parity assertions' outcomes | `regression.md` |
| T13 | the sample app used, the `uvicorn` boot log, and the `curl` responses for `/health`, an authorized call and an unauthorized one | `manual-embedding.md` |
| T14 | `make lint typecheck` output | `gates.md` |

Redaction: the captures are local test output with no tokens, hostnames or personal data;
absolute paths under the working checkout are rewritten to repository-relative before
committing.

## Verification activities

- [x] T1 — `uv run --project cli pytest tests/test_sdk_client.py tests/test_sdk_environment.py -q`
- [x] T2 — `uv run --project cli pytest tests/test_sdk_embedding_integration.py -q`
- [x] T3 — `uv run --project cli pytest tests/test_api_contract_parity.py -q`
- [x] T4 — `uv run --project cli pytest -q` (the whole suite, nothing adapted)
- [x] T5 — `uv run --project cli pytest tests/test_sdk_docs_parity.py -q`
- [x] T10 — `uv run --project cli pytest tests/test_sdk_security_integration.py -q`
- [x] T13 — serve the documented quickstart with `uvicorn` and exercise it with `curl`
- [x] T14 — `make lint typecheck`

## Verification results

Executed 2026-08-15 on `claude/github-issue-212-n81fy7`. Every activity ran; none was
replanned or escalated.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `pytest cli/tests/test_sdk_client.py cli/tests/test_sdk_environment.py -q` | 38 passed | [`tests.md`](evidence/tests.md) |
| T2 | `pytest cli/tests/test_sdk_embedding_integration.py -v` | 10 passed, each Gherkin-documented | [`tests.md`](evidence/tests.md) |
| T3 | `pytest cli/tests/test_api_contract_parity.py -q` | 2 passed — router == served app == authored contract | [`regression.md`](evidence/regression.md) |
| T4 | `pytest -q cli`, run twice: after the refactor alone, and with the SDK | 2041 passed / 1 skipped with **no test adapted**, then 2098 passed / 1 skipped | [`regression.md`](evidence/regression.md) |
| T5 | `pytest cli/tests/test_sdk_docs_parity.py -q` | 4 passed | [`regression.md`](evidence/regression.md) |
| T10 | `pytest cli/tests/test_sdk_security_integration.py -q` | 4 passed; the dependency case walks all 29 operations from the host's own OpenAPI document | [`tests.md`](evidence/tests.md) |
| T13 | the documented quickstart under a real `uvicorn`, exercised with `curl` | ran as written; 401/200/404/400/MCP-200 as documented | [`manual-embedding.md`](evidence/manual-embedding.md) |
| T14 | `ruff check` · `ruff format --check` · `pyright cli` · `markdownlint-cli2` · `validate_config.py` | all clean (671 markdown files, 0 errors; pyright 0 errors) | [`gates.md`](evidence/gates.md) |

**Not executed:** none. The six `n/a` rows in the matrix were declared at `test-planning`
with reasons and are unchanged.

## Review comments

*None yet.*
