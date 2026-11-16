---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#532"
status: draft                # design-approval skipped by declaration at phase-selection
approvedBy: []
overrides: {}
---

<!-- Written per the `the-loop:writing` skill. -->

# Testing plan: graph notifications on a gateway consumer post first time

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `build_runtime` seeds `gateway` + `instance`; `posting_path` resolves `gateway` with no token; no block → no gateway | `cd cli && pytest tests/test_graph_gateway_notify.py` |
| T2 | Integration (scenario) | yes | the real `notify` hook on a gateway-consumer runtime posts through the gateway on the first attempt, under the instance's name, outbox empty | `cd cli && pytest tests/test_graph_gateway_notify_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API surface changes | | |
| T4 | End-to-end | n/a — a live gateway + Slack workspace isn't available in this session; T2 drives the real hook → bus → channel → gateway client path with only the HTTP call replaced | | |
| T5 | UI / visual | n/a — no UI | | |
| T6 | Snapshot | n/a — no rendered output changes | | |
| T7 | Performance / load | n/a — two dict entries | | |
| T8 | Security / abuse case | yes | a config with no / malformed `gateway` block still yields no gateway path (fail-closed unchanged) | part of T1 |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | n/a — no schema or state change | | |
| T11 | Manual exploratory | n/a — covered by T2 | | |
| T12 | Regression suite | yes | nothing else in the CLI breaks | `cd cli && pytest -q -x -n auto` (or plain `pytest -q`) |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.2, R1.4, R2.1 | runtime config carries both keys; gateway path; no block → no gateway |
| T2 | R1.2, R1.3, R2.1 | `Scenario: a graph notification on a gateway consumer posts through the gateway on the first attempt` |
| T8 | R1.4 | no / malformed block → `posting_path(...).kind == "none"` |
| T12 | — | full suite green |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. The gateway's HTTP call is replaced in-process.
- **Fixtures & data:** a `tmp_path` state root; a literal CLI config.
- **Credentials:** none. The test unsets the bot-token variable it names.
- **Bring-up:** `cd cli && pip install -e '.[dev]'` (already installed in the dev env)
  · **Tear-down:** none.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8 | red (before fix) and green (after) runs | `unit.md` |
| T12 | full-suite summary | `regression.md` |

## Verification activities

- [ ] T1 — `cd cli && pytest tests/test_graph_gateway_notify.py`
- [ ] T2 — `cd cli && pytest tests/test_graph_gateway_notify_integration.py`
- [ ] T8 — covered by T1's negative cases
- [ ] T12 — `cd cli && pytest -q`

## Verification results

_Not yet executed._

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |

## Review comments
