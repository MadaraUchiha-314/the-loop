---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#274"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: the session that opens a pull request is the one that records it

> Derived from the approved `bugfix.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `core.sessions.link_pull_request`: the happy path and its `session.pr_linked`, idempotence, no session record, self-link, bare-number / `#N` / cross-repository resolution, malformed refs | `make test` (`uv run pytest cli/tests`) |
| T2 | Integration (scenario) | yes | the reproduction end to end — a review comment on a the-loop-authored spec PR (no closing reference, `loop/…` branch, no closing keyword) is dropped as `awaiting-start` without the binding and delivered into the work item's session with it — Gherkin-documented | `make test` |
| T3 | Contract (OpenAPI) | yes | the authored `the-loop.v1.yaml` and the served schema both carry `POST /api/v1/sessions/link-pr` / `linkSessionPullRequest`, and the embeddable router carries it too | `make test` (`test_api_contract_parity.py`) |
| T4 | End-to-end | n/a — an E2E run needs a real GitHub repository, a real `gh` credential and a real tmux/harness. T2 drives the real `Dispatcher`, the real `SessionRegistry` and the real router against injected tmux/provider fakes, which is how this path has always been proved in this repo | | |
| T5 | UI / visual | n/a — no user-facing surface; the change is a CLI action, an API route, an MCP tool and documentation | | |
| T6 | Snapshot | n/a — no rendered artefact changes | | |
| T7 | Performance / load | n/a — one appended endpoint per pull request, written once by an operator-initiated call. Nothing on a hot path changes | | |
| T8 | Security / abuse case | yes | the operation cannot create a work item (no record → no write), cannot link a work item to itself, and refuses a malformed ref before touching the filesystem | `make test` |
| T9 | Accessibility | n/a — no user interface | | |
| T10 | Migration / upgrade | n/a — no state shape changes. The endpoint written is the `pullRequests[]` entry the registry has held since issue-172, and a record without one is exactly today's record | | |
| T11 | Manual exploratory | n/a — the reproduction is mechanised as T2, which is stricter than the observed symptom: it asserts which session the event reached, not merely that it was not dropped | | |
| T12 | Static analysis (lint + types) | yes | `ruff`, `pyright`, `markdownlint` over the changed modules and docs | `make lint` |
| T13 | Docs ↔ code parity | yes | the CLI, SDK and event-catalogue documentation still match the code (`test_docs_parity.py`, `test_sdk_docs_parity.py`, `test_writing_parity.py`, `test_eventlog.py`) | `make test` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.2 | a pull request not yet listed is added to the record and `session.pr_linked` is emitted once |
| T1 | R1.3 | a second call for the same pair rewrites nothing, emits nothing, and still exits 0 |
| T1 | R1.4 | a work item with no session record: exit 1, no file written |
| T1 | R1.5 | linking a work item to itself: exit 2 |
| T1 | R1.6 | `--pull-request 275`, `--pull-request '#275'` and a full ref in **another** repository all resolve to the intended endpoint |
| T1 | R1.7 | a malformed work-item ref, a malformed pull-request ref and a non-positive number are all exit 2, nothing written |
| T1 | R1.1 | the CLI action, the HTTP route and the MCP tool all reach the one core function |
| T2 | R1.2, R3.2 | `Scenario: a review comment on a spec PR the-loop opened reaches the work item's session` — with and without the binding |
| T3 | R1.1 | the served schema, the authored contract and the embeddable router agree on `linkSessionPullRequest` |
| T8 | Security design | no record → no write; self-link refused; malformed ref refused before the registry is opened |
| T13 | R2.1, R2.2, R2.4 | the skill, the two commands, the execution-log template and the capability doc carry the rule; the new SDK method is documented (P1) and reaches core (P2); the event catalogue still matches what is emitted |
| T12 | R3.1 | lint and type checks pass over the changed modules |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. No tmux, no harness, no network: the dispatcher's tmux
  runner is an injected fake, as in `cli/tests/test_routing.py`, and the CLI tests run on
  the in-process seam (`THE_LOOP_SERVICE_LOCAL=1`) rather than standing a service up.
- **Fixtures & data:** the existing registry/dispatcher fixtures; `tmp_path` for the state
  root so the record is asserted on disk.
- **Credentials:** none. No `gh` is invoked by any path under test.
- **Bring-up:** `make test` · **Tear-down:** none (pytest `tmp_path`).
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T3, T8 | red run — the new tests, run before any production code changed | `red.md` |
| T1, T2, T3, T8, T13 | green run — full suite summary and the per-file runs | `unit-and-integration.md` |
| T12 | `make lint` / type-check output | `lint-and-typecheck.md` |
| — | security review record (checklist per `reference/security.md`) | `security-review.md` |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_core_sessions.py cli/tests/test_cli.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_webhook_routing_integration.py`
- [x] T3 — `uv run --project cli python -m pytest -q cli/tests/test_api_contract_parity.py cli/tests/test_api_routers_integration.py cli/tests/test_mcp_integration.py`
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests/test_core_sessions.py -k link`
- [x] T13 — `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py cli/tests/test_sdk_docs_parity.py cli/tests/test_writing_parity.py cli/tests/test_eventlog.py`
- [x] T12 — `make lint` (`ruff check`, `ruff format --check`, `markdownlint-cli2`) and `uv run pyright cli`
- [x] Full suite — `make test`
- [x] Red run captured before the fix — `evidence/red.md`
- [x] Security review — the checklist in `reference/security.md`, against the diff

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|---|---|---|---|
| Red run | the 19 new tests, written and run **before** any production code changed | 18 failed, 1 passed — the pass is the control, which asserts the bug and passes on both sides of the fix | [`evidence/red.md`](evidence/red.md) |
| T1 | `pytest -q cli/tests/test_core_sessions.py cli/tests/test_cli.py` and `pytest -q cli/tests/test_routing.py -k link_pr` | 68 passed; 2 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T2 | `pytest -q cli/tests/test_webhook_routing_integration.py` | 29 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T3 | `pytest -q cli/tests/test_api_contract_parity.py cli/tests/test_api_routers_integration.py cli/tests/test_mcp_integration.py` | 18 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T8 | `pytest -q cli/tests/test_core_sessions.py -k link` | 16 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T13 | `pytest -q cli/tests/test_docs_parity.py cli/tests/test_sdk_docs_parity.py cli/tests/test_writing_parity.py cli/tests/test_eventlog.py` | 35 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| Full suite | `make test` | **2501 passed, 1 skipped** after rebasing onto `main` at `71e7dff`; pre-rebase, on `main` at `50c2a27`: 2495 passed, 1 skipped, up from 2476 — the 19 this work item adds | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T12 | `uv run ruff check cli hooks`, `uv run ruff format --check cli hooks`, `uv run pyright cli`, `markdownlint-cli2` (850 files), `scripts/validate_config.py` | clean on the first run of each | [`evidence/lint-and-typecheck.md`](evidence/lint-and-typecheck.md) |
| Security review | checklist (`reference/security.md`), effective risk tier 3 | pass, no findings | [`evidence/security-review.md`](evidence/security-review.md) |

Every planned activity ran. One row was **replanned** before it ran: T13 named
`test_harness_usage.py`, which turned out to be the harness token-telemetry parser and has
nothing to do with documentation parity. It is replaced by `test_sdk_docs_parity.py` and
`test_eventlog.py` — the two parity tests this change actually has to satisfy. Nothing is
left unticked.
