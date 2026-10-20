---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#505"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: the gateway learns a work item's collaboration channel

Four kinds of check prove this change: unit tests on the store, the Slack resolution, the
consume route, the client and the store hook; one Gherkin-documented hosted integration
test that replays the ticket's reproduction; abuse-case tests for each row of
`design.md` § Security design; and the OpenAPI contract parity test. Everything runs in
this repository with `pytest`, against an in-process gateway (`tests/gateway_support.py`).
Nothing needs Slack.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `publish_rooms` / `resolve_room` / `rooms_of`, the backlog drain, pruning; `_resolve_slack` order; `CollaborationChannelStore.on_change`; `GatewayClient.publish_rooms`, `register`, the reconcile throttle | `cd cli && uv run python -m pytest -q tests/test_gateway_rooms.py` |
| T2 | Integration (scenario) | yes | the ticket's reproduction through the HTTP consume API and the Slack ingress: a collaborator's top-level message routes `by: claim`; a held backlog drains; retraction; re-registration after a store loss. Gherkin-documented | `cd cli && uv run python -m pytest -q tests/test_gateway_rooms_integration.py` |
| T3 | Contract (OpenAPI) | yes | `PUT /api/v1/gateway/rooms` is in `the-loop-gateway.v1.yaml` and the served surface matches | `cd cli && uv run python -m pytest -q tests/test_api_contract_parity.py` |
| T4 | End-to-end | n/a — a live run needs a gateway, an instance and a real Slack app. T2 drives the same HTTP routes and ingress the gateway serves, with a fake Slack payload | | |
| T5 | UI / visual | n/a — no visual surface | | |
| T6 | Snapshot | n/a — JSON answers are asserted field by field | | |
| T7 | Performance / load | n/a — one indexed lookup per unbound Slack event, and a directory scan every 30 s that the poll transport already does | | |
| T8 | Security / abuse case | yes | abuse cases 1–5: allow-list, live holder kept, other instance's room untouched, malformed or oversized body → 422, a stranger's routed message still checked by the instance; an unreadable portable dir does not retract | `cd cli && uv run python -m pytest -q tests/test_gateway_rooms.py tests/test_gateway_rooms_integration.py -k abuse` |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | yes | a store created by 20.4.0 (no `rooms` table) opens and gains it; existing events and bindings survive | `cd cli && uv run python -m pytest -q tests/test_gateway_rooms.py -k migration` |
| T11 | Regression (whole suite) | yes | behaviour preserved without rooms; the full suite, lint, format, types and markdown | `uv run pre-commit run --all-files` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.5 | the client publishes `targets()`; a contested channel is not published |
| T1 | R1.2 | `add` / `remove` / `clear` call `on_change`; an unchanged `add` does not; a raising hook does not fail `add` |
| T1 | R1.3 | `step()` reconciles only after `ROOMS_RECONCILE_S`; an unchanged set makes no call |
| T1 | R1.4 | `register()` publishes the full set even when unchanged |
| T1 | R1.6 | a transport error or a 500 logs a warning and returns `False`; the next reconcile retries |
| T1 | R2.1, R2.3, R2.4 | resolution order: thread binding → published room → static room → held |
| T1 | R3.1–R3.3 | drain re-subjects and routes held `<channel>:*` events in order; held on the subject without claimants, routed by a later claim; routed events untouched; another channel's held events untouched |
| T1 | R4.1, R4.2, R4.4 | a set without a room deletes it; a moved room swaps |
| T1 | R4.5 | pruning a lapsed instance drops its rooms |
| T1 | R5.1–R5.3 | a live holder's room refused, the rest applied; an expired holder taken over; another instance's room untouched |
| T1 | R7.1 | `rooms_of` / `GET /instances` lists rooms |
| T2 | R1.1, R2.2, R6.1 | `Scenario: a collaborator's top-level message in a declared room reaches the work item` |
| T2 | R3.1 | `Scenario: messages held before the room was published are routed when it is` |
| T2 | R4.1, R4.3 | `Scenario: clearing the declaration retracts the room` |
| T2 | R1.4 | `Scenario: a gateway that lost its store gets the rooms back on re-registration` |
| T2 | R7.2 | `gateway.rooms` and `gateway.refused` records asserted in the scenarios above |
| T3 | NFR contract | parity of path, method and operationId |
| T8 | R5.4, abuse 1 | an instance outside `consume.allowedInstances` → refused; a second peer under a live name → 409 |
| T8 | abuse 2, 3 | covered by the R5.1–R5.3 cases, run under `-k abuse` |
| T8 | abuse 5 | a key that is not a Slack id, a ref that does not parse, more than `ROOMS_MAX` rooms → 422 and nothing stored |
| T8 | fail closed | `targets()` over an unreadable directory → no publish |
| T10 | NFR store compatibility | open a store made with the 20.4.0 schema, then publish a room |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. The gateway runs in-process through FastAPI's
  `TestClient` (`GatewayHarness`); the instance side uses `GatewayClient` with an
  in-process transport, as `test_gateway_client_integration.py` does.
- **Fixtures & data:** `tmp_path` stores and portable directories; Slack event payloads
  built in the test.
- **Credentials:** none.
- **Bring-up:** `uv sync --locked` · **Tear-down:** none.
- **If bring-up fails:** record it below, leave the dependent activities unticked, and
  escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T8, T10 | pytest summary and red → green note | `unit.md` |
| T2 | scenario list (`the-loop scenarios`) and run output | `integration.md` |
| T3 | parity test output and the operation list | `contract.md` |
| T11 | pre-commit summary | `lint-and-typecheck.md` |

## Verification activities

- [ ] T1 — `cd cli && uv run python -m pytest -q tests/test_gateway_rooms.py`
- [ ] T2 — `cd cli && uv run python -m pytest -q tests/test_gateway_rooms_integration.py`
- [ ] T3 — `cd cli && uv run python -m pytest -q tests/test_api_contract_parity.py`
- [ ] T8 — `cd cli && uv run python -m pytest -q tests/test_gateway_rooms.py tests/test_gateway_rooms_integration.py -k abuse`
- [ ] T10 — `cd cli && uv run python -m pytest -q tests/test_gateway_rooms.py -k migration`
- [ ] T11 — `uv run pre-commit run --all-files`

## Verification results

## Review comments
