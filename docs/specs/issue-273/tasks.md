---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#273"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Tasks: let the gate that precedes the spec run before the spec exists

> The last spec artifact (bugfix → design → testing plan → tasks). Derived from the approved
> `design.md` and `testing-plan.md`.

## Task list

- [x] 1. The predicate names its exempt actions
  - `_SPEC_DIR_OPTIONAL_ACTIONS = frozenset({"start", "context"})` beside `_ADOPTING_ACTIONS`,
    carrying the reasoning for each member and each non-member; `_guarded`'s `is_dir()` gate
    consults it. Nothing above it in the gate order moves.
  - _Depends on:_ none
  - _Requirements:_ R1.1, R1.4, R1.5, R1.6
  - _Test:_ `T1 — uv run pytest cli/tests/test_graphlink.py -k "spec_directory or skip"` (red→green)
- [x] 2. A work item that has not been placed still resolves a context
  - `GraphLink._pending_context`; `_context_from` delegates to it instead of returning
    `None`; `GraphContext.status` documents `pending` and why it is not `at_human_gate`.
  - _Depends on:_ 1 (the context of an unplaced item is unreachable without the exemption)
  - _Requirements:_ R2.1, R2.3, R2.4, R2.6
  - _Test:_ `T1 — uv run pytest cli/tests/test_graph_drive.py -k about_to_stand` (red→green)
- [x] 3. The `pending` block says what the session may not do
  - `render_graph_context` short-circuits on `status == "pending"`: the NOT-ENTERED-YET line,
    the human-gate line when the node's actor is `human`, the trailer — and none of the
    resume, claim or surface lines that describe an entered node.
  - _Depends on:_ 2
  - _Requirements:_ R2.2, R2.5
  - _Test:_ `T2 — uv run pytest cli/tests/test_graphlink_integration.py -k forbids_starting` (red→green)
- [x] 4. The reproduction, end to end
  - Gherkin-documented scenarios against a real `Dispatcher` and a real `Runtime` over the
    shipped graph: a plain-ticket spawn is held at `phase-selection` with the label set and
    the checklist posted; an unauthorized `the-loop execute` moves nothing; a started graph
    still reports its real node. Plus `_bare_checkout` and an offline provider fixture.
  - _Depends on:_ 1, 2, 3
  - _Requirements:_ R1.1, R1.2, R1.3, R2.3, R4.2
  - _Test:_ `T2, T8, T10 — uv run pytest cli/tests/test_graphlink_integration.py`
- [x] 5. The tests that pinned the old behaviour say what they pin now
  - `test_a_work_item_with_no_spec_directory_is_skipped` → `…_is_still_started`, with the
    reason the original reading was answered by `_awaiting_start` all along; the event-log
    skip test driven by an `advance`; the `specDir` parity test split across a gated and an
    exempt action; the scaffold suite's spawn now starts a graph, so it gains an autouse
    offline provider and asserts `graph-state.json` instead of its absence.
  - _Depends on:_ 1, 2
  - _Requirements:_ R1.4, R1.5, R4.1
  - _Test:_ `T1 — uv run pytest cli/tests/test_graphlink.py cli/tests/test_harness_config_scaffold_integration.py`
- [x] 6. Write it down
  - `docs/capabilities/process-graph.md`: which actions require the spec directory and why
    the split falls there; the `pending` context and its block; a history row.
    `docs/capabilities/webhook-triggers.md`: correct the list of when `$graph_context`
    renders empty; note the exemption beside the `specDir` paragraph; a history row.
  - _Depends on:_ none
  - _Requirements:_ R3.1, R3.2, R3.3
  - _Test:_ `T12 — make lint`
- [x] 7. Verify and evidence
  - Run every activity in the testing plan, record the results in it, and file the red run,
    the green runs, the lint/type-check output and the security review under `evidence/`.
  - _Depends on:_ 1–6
  - _Requirements:_ R4.1, R4.2
  - _Test:_ `make test`, `make lint`, `make typecheck`

## Execution notes

Task 2 depends on task 1 for a reason worth stating: the `pending` context is only reachable
for an unplaced work item once `context` is exempt from the directory check. Shipping either
half alone leaves the bug half-fixed — the graph starting but the prompt still silent, or the
prompt describing a node the graph declined to enter.
