---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#532"
status: draft
approvedBy: []
overrides: {}
---

<!-- Written per the `the-loop:writing` skill. -->

# Tasks: graph notifications on a gateway consumer post first time

## Task list

- [x] 1. Write the failing tests
  - Unit: `cli/tests/test_graph_gateway_notify.py` — runtime config carries `gateway`
    and `instance`; `posting_path` is `gateway` with no token; no / malformed block → `none`.
  - Integration: `cli/tests/test_graph_gateway_notify_integration.py` — the real
    `notify` hook posts through the gateway client on the first attempt under the
    instance's name; outbox empty.
  - Watch them go red.
  - _Depends on:_ none
  - _Requirements:_ R1.1–R1.4, R2.1
  - _Test:_ T1, T2, T8 (red)
- [x] 2. Seed `gateway` and `instance` in `build_runtime`
  - `cli/the_loop/graph/bootstrap.py`, next to `channels` and `state`, with a comment
    naming the readers.
  - _Depends on:_ 1
  - _Requirements:_ R1.1–R1.4
  - _Test:_ T1, T2, T8 (green)
- [x] 3. Capability doc + full suite
  - Note the seeded keys in the channels / gateway capability doc that describes the
    posting path.
  - _Depends on:_ 2
  - _Requirements:_ —
  - _Test:_ T12

## Dependency graph (DAG)

`1 → 2 → 3`

## Checkpoints

After task 2 run T1/T2; after task 3 run T12. Verification then executes
`testing-plan.md`.

## Review comments
