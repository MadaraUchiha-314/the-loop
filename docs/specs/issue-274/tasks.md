---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#274"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Tasks: the session that opens a pull request is the one that records it

> The last spec artifact (bugfix → design → testing plan → tasks). Derived from the approved
> `design.md` and `testing-plan.md`.

## Task list

- [x] 1. Red run — the tests, before the code
  - Every case in `testing-plan.md` T1/T2/T8, written against the interfaces `design.md`
    names, and captured failing in `evidence/red.md`.
  - _Depends on:_ none
  - _Requirements:_ R3.1, R3.2
  - _Test:_ `uv run pytest cli/tests/test_core_sessions.py cli/tests/test_webhook_routing_integration.py -k link` (red)
- [x] 2. `core.sessions.link_pull_request`
  - Parse the work item; resolve the pull request (bare number / `#N` → the work item's
    repository, otherwise a full ref); refuse a self-link; exit 1 with no write when the
    work item has no record; otherwise `SessionRegistry.link_pull_request` and render the
    linked / already-linked message.
  - _Depends on:_ 1
  - _Requirements:_ R1.1–R1.7
  - _Test:_ `T1, T8 — uv run pytest cli/tests/test_core_sessions.py -k link` (red→green)
- [x] 3. The three surfaces
  - CLI `sessions link-pr` (`routed()` + `_render` + `_report`, like its siblings);
    `POST /api/v1/sessions/link-pr` with `SessionLinkPrBody` and
    `operationId: linkSessionPullRequest`; the MCP `link_pull_request` tool, registered.
  - _Depends on:_ 2
  - _Requirements:_ R1.1
  - _Test:_ `T1, T3 — uv run pytest cli/tests/test_cli.py cli/tests/test_api_contract_parity.py cli/tests/test_api_routers_integration.py cli/tests/test_mcp_integration.py`
- [x] 4. The authored OpenAPI contract
  - `docs/api-specs/openapi/the-loop.v1.yaml`: the path, the response and the
    `SessionLinkPrBody` schema — the contract is the source of truth, the served schema
    must match it.
  - _Depends on:_ 3
  - _Requirements:_ R1.1
  - _Test:_ `T3 — uv run pytest cli/tests/test_api_contract_parity.py`
- [x] 5. The reproduction, end to end
  - A Gherkin-documented integration scenario: a `pull_request_review_comment` on a pull
    request with no closing reference, a `loop/<id>-requirements` branch and a body that
    only mentions the issue — dropped as `awaiting-start` without the binding, delivered
    into the work item's existing session with it.
  - _Depends on:_ 2
  - _Requirements:_ R1.2, R3.2
  - _Test:_ `T2 — uv run pytest cli/tests/test_webhook_routing_integration.py -k link` (red→green)
- [x] 6. The workflow rule (R2)
  - `skills/the-loop/reference/automation.md` (the command and why inference is not
    enough), `commands/work-on.md`, `commands/execute-tasks.md`,
    `skills/the-loop/templates/execution-log.md`.
  - _Depends on:_ 3
  - _Requirements:_ R2.1, R2.2, R2.3
  - _Test:_ `T13 — uv run pytest cli/tests/test_harness_usage.py cli/tests/test_writing_parity.py`
- [x] 7. The documentation (R2.4)
  - `docs/cli/commands/sessions.md` (the action and its flags), `docs/cli/service.md` (the
    routed-operations table), `docs/capabilities/cli.md`, and
    `docs/capabilities/webhook-triggers.md` — the binding as a linkage source the-loop
    **writes**, with its history row. Event catalogue: `session.pr_linked` names its new
    writer.
  - _Depends on:_ 3
  - _Requirements:_ R2.4
  - _Test:_ `T13 — uv run pytest cli/tests/test_docs_parity.py cli/tests/test_eventlog.py`
- [x] 8. Verification, evidence and review
  - Run every activity in `testing-plan.md`, record the results and commit the evidence;
    self-review ×3 and critic-review ×3 per `reviews`; security review per
    `reference/security.md`; the reviewer briefing on the PR.
  - _Depends on:_ 1–7
  - _Requirements:_ R3.1, R3.2
  - _Test:_ `make check`
