---
type: testing-plan
phase: test-planning
workItem: issue-199
status: approved
approvedBy: []
overrides: {}
---

# Testing plan: a contribution has no outer loop, and its arming comment answers its first gate

> Derived from the approved `bugfix.md` and `design.md`, **before** `tasks.md` — each
> task's `_Test:_` names a row below. Authored at `test-planning`, completed at
> `verification`.
>
> **This file is executable content.** It names commands an agent will run. No credential
> appears here, by value or by reference: every test runs offline against a fake GitHub
> integration and a temporary checkout.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the checklist, the parse, the confirmation and the frozen record for a contribution — and unchanged for the outer loop | `uv run --project cli python -m pytest -q cli/tests/test_graph_contribution.py` |
| T2 | Integration (scenario) | yes | a real `GraphLink` over a real `Runtime` and a fake GitHub: `on_spawn` carries an arming comment's goal to `phase-selection`; no goal parks; a respawn changes nothing | `uv run --project cli python -m pytest -q cli/tests/test_graph_contribution.py -k spawn` |
| T3 | Integration (dispatcher) | yes | the spawning `RoutedEvent` reaches `on_spawn`, on the shared dispatcher both ingresses use | `uv run --project cli python -m pytest -q cli/tests/test_graph_drive_integration.py` |
| T4 | Unit (prompt) | yes | `$graph_context` names no outer loop for a contribution, and still places one for every other loop; an agent start node is not evaluated at spawn | `uv run --project cli python -m pytest -q cli/tests/test_graph_drive.py` |
| T5 | Contract (OpenAPI) | n/a — no API request or response shape changes; `graph-state.json` keeps its fields and `surface` keeps its type. `test_api_contract_parity.py` runs as part of T6 and would catch it if that were wrong. | | |
| T6 | Regression (whole suite) | yes | the spawn path now runs an exit chain that never ran before; nothing else may move | `make test` |
| T7 | UI / visual | n/a — no rendered UI; the two user-visible surfaces are a comment body and a prompt block, both asserted as text in T1/T4. | | |
| T8 | Snapshot | n/a — no serialized artifact whose whole shape is asserted; the frozen record's changed field is asserted by name in T1. | | |
| T9 | Performance / load | n/a — one extra exit-chain evaluation per **fresh** spawn of a human start node, on a path that has just started a tmux session and an LLM; unmeasurable beside it, and zero for every other spawn. | | |
| T10 | Security / abuse case | yes | the three abuse cases in `bugfix.md` § Security considerations, each as a negative test | `uv run --project cli python -m pytest -q cli/tests/test_graph_contribution.py -k unauthorized or surface` |
| T11 | Accessibility | n/a — no rendered UI. | | |
| T12 | Migration / upgrade | yes | a work item frozen by 9.6.0 with `surface: work-item` still reads as before; a contribution written by this version carries `""`, which every reader already treats as the default | covered by T1 and by the pre-existing state round-trip tests in T6 |
| T13 | Manual exploratory | n/a — the reproduction needs a live daemon, a watched repository and credentials; T2 and T3 reproduce both halves deterministically and offline against the same code paths, which is stronger evidence than one manual run. | | |
| T14 | Lint / typecheck / docs parity | yes | ruff, ruff-format, pyright, config validation, markdownlint and `test_docs_parity.py` | `make check` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1 | the contribution checklist carries no `outer-loop-on-pull-request` row and says where the conversation happens |
| T1 | R1.2 | the work-item loop's checklist still carries it, worded as before |
| T1 | R1.3, R1.4 | a reply ticking the token on a contribution: pointer advances, `state.surface == ""`, frozen `surface == ""`, no phase declared away, confirmation silent about a surface |
| T2 | R2.1 | a spawn whose arming comment states the goal lands the item at `phase-selection`, checklist posted, binding recorded |
| T2 | R2.2 | a spawn with no goal parks at `goal-definition` carrying the gate's own reason |
| T2 | R2.3 | a second `on_spawn` re-records the binding and leaves every node record untouched, even once the goal has become answerable |
| T3 | R2.1 | the dispatcher hands the spawning `RoutedEvent` to the graph coupling |
| T4 | R1.5 | a contribution's prompt block says "a contribution has no outer loop" and never "the outer loop's artifacts" |
| T4 | R1.2 | a work item's prompt block still places the outer loop on its chosen surface |
| T4 | R2.4 | an agent start node is entered and **not** evaluated: not parked, no block recorded, one attempt |
| T10 | abuse 1 | an unauthorized goal in the thread leaves the gate waiting (pre-existing coverage, re-run) |
| T10 | abuse 2 | the injected surface token is inert (same case as T1/R1.3) |
| T10 | abuse 3 | an integration outage during the gate leaves the item waiting, never guessing (pre-existing coverage, re-run) |
| T6 | R2.5 | the whole suite: every other spawn path, every other loop, unchanged |
| T14 | R3.1 | docs parity over the changed CLI page and capability docs |

## Verification environment

A temporary directory per test (`tmp_path`) holding `docs/specs/issue-9/`, the shipped
graphs from the package, and a fake GitHub integration injected at
`the_loop.graph.integrations.resolve`. No network, no credentials, no tmux; the
dispatcher rows use the suite's `FakeTmux` and `StubInteractiveAdapter`.

## Verification results

_Executed at `verification` — see `evidence/`._

| # | Result | Evidence |
|---|--------|----------|
| T1 | pass | [`evidence/unit.md`](evidence/unit.md) |
| T2 | pass | [`evidence/unit.md`](evidence/unit.md) |
| T3 | pass | [`evidence/integration.md`](evidence/integration.md) |
| T4 | pass | [`evidence/unit.md`](evidence/unit.md) |
| T6 | pass | [`evidence/check.md`](evidence/check.md) |
| T10 | pass | [`evidence/unit.md`](evidence/unit.md) |
| T12 | pass | [`evidence/unit.md`](evidence/unit.md) |
| T14 | pass | [`evidence/check.md`](evidence/check.md) |
