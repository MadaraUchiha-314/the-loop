---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#377"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: a released work item is launched with the arguments the operator declared

> Derived from `bugfix.md` and `design.md`, **before** `tasks.md` — each task's `_Test:_`
> names a row of the matrix below. Authored at `test-planning`, completed at
> `verification`. See `reference/testing.md`.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. Nothing here needs credentials, the network, `tmux` or a harness binary: the
> runner is the `FakeTmux` double every dispatcher test uses, the adapter's availability
> and environment preparation are stubbed on the real `ClaudeCodeAdapter`, and the graph
> link is a double that freezes a choice into a real `work-item-state.json` under
> `tmp_path` when the gate is answered.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `launch_args`: the new home alone, the deprecated home alone, both (new wins, and `config_findings` reports the conflict), neither (empty dict), a non-list `args` (falls back) (R1.1, R1.3, R1.4) | `cli/tests/test_modelchoice.py` |
| T2 | Integration (scenario) | yes | **The report's check.** The dispatcher composed by `poller.daemon._build_dispatcher` from a config declaring the flag under `harnesses[].args` only: an `issue_comment` releases a parked work item and the recorded argv — the session record and the `session.spawned` event — contains every configured argument (R1.1, R1.5, R4.1) | `cli/tests/test_spawn_gate_integration.py` |
| T3 | Integration (scenario) | yes | The same composition with the deprecated `routing.harnessArgs` only still launches with the arguments (R1.1) | `cli/tests/test_spawn_gate_integration.py` |
| T4 | Integration (scenario) | yes | A model the gate-answering reply froze reaches the argv of the session that reply spawns, its record carries the model, and the next event is delivered into it rather than re-launching it (R2.1, R2.2, R4.2) | `cli/tests/test_spawn_gate_integration.py` |
| T5 | Unit | yes | `_adapter_for`: a work item that chose nothing launches on the adapter's own arguments (now built from `harnesses[].args`); one that chose launches on those same arguments followed by the model's and the effort's; the fixture builds its adapter through `launch_args` so the choice suite exercises the real wiring (R1.2) | `cli/tests/test_dispatcher_choice.py` |
| T6 | Unit | yes | `session.spawned` / `session.respawned` carry `harness_args`, `model` and `effort`; `session.pr_spawned` carries `harness_args` (R1.5) | `cli/tests/test_spawn_gate_integration.py` (spawn) and `cli/tests/test_dispatcher_choice.py` (respawn), reading the log `eventlog.configure` wrote |
| T7 | Unit | yes | A standing-session entry that omits `harnessArgs` inherits `harnesses[].args`; `[]` still means none; `create_standing` inherits the same way (R3.2) | `cli/tests/test_standing.py`, `cli/tests/test_standing_integration.py` |
| T8 | Unit | yes | `the-loop models check` builds its probe adapters from `launch_args`, so the probed argv carries `harnesses[].args` (R3.1) | `cli/tests/test_models_cmd.py` |
| T9 | Security / abuse case | yes | A1 on the newly reachable path: a `work-item-state.json` naming an undeclared model, frozen by the reply that spawns the session, contributes nothing to the argv; the existing abuse table of `test_dispatcher_choice.py` runs unmodified against the rewired fixture (A1, A3, A4) | `cli/tests/test_spawn_gate_integration.py`, `cli/tests/test_dispatcher_choice.py` |
| T10 | Regression | yes | The full suite, unmodified except where a fixture asserted the bug (`test_a_work_item_that_chose_nothing_gets_the_shared_adapter_untouched` — the adapter is still untouched, and now carries the declared arguments) | `uv run --project cli python -m pytest -q cli` |
| T11 | Docs parity | yes | The docs↔code parity tests and the schema-copy parity test stay green; the event catalogue entries name the new fields | `cli/tests/test_docs_parity.py`, `cli/tests/test_config_schema_parity.py` |
| T12 | Contract (OpenAPI) | n/a | — no route, parameter or schema shape changes; one `description` string in the authored contract is reworded to name both homes, which the parity test does not compare | — |
| T13 | End-to-end | n/a | — the daemon composition is exercised in T2–T4 with the runner and the harness binary stubbed; a real `tmux` + `claude` run is the operator's T15 | — |
| T14 | Performance | n/a | — one dict built at daemon start/reload; a spawn does one fewer config read | — |
| T15 | Manual / exploratory | yes | On a devbox running the fix with the flag declared under `harnesses[].args`: label an issue, answer the gate, and confirm `ps -eo pid,cmd \| grep "[c]laude --session-id"` shows the flag and `the-loop events --type session.spawned` shows `harness_args` — the report's own procedure | operator-run; recorded in `evidence/final-validation.md` as not reproducible here |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.3, R1.4 | `launch_args` precedence table |
| T2 | R1.1, R1.5, R4.1 | `Scenario: a session released from the human-start gate is launched with every configured harness argument` |
| T3 | R1.1 | `Scenario: the deprecated routing.harnessArgs still reaches a released session` |
| T4 | R2.1, R2.2, R4.2 | `Scenario: the session spawned by the gate-answering reply already runs on the model it froze` |
| T5 | R1.2 | the choice path's argv is the shared adapter's plus the choice |
| T6 | R1.5 | the spawn events carry the argv |
| T7 | R3.2 | standing sessions inherit the resolved arguments |
| T8 | R3.1 | the probe uses the resolved arguments |
| T9 | A1 | `Scenario: a forged model in the state file buys nothing on the post-gate spawn` |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none — no `tmux`, no harness binary, no `gh`, no network.
- **Fixtures & data:** `cli/tests/conftest.py`'s `FakeTmux` and the hermetic event log;
  a `work-item-state.json` written under `tmp_path` by the test's graph-link double.
- **Credentials:** none.
- **Bring-up:** `uv sync` · **Tear-down:** none.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1–T11 | per-row command, outcome and the test names, plus the gate commands (`ruff`, `pyright`, `validate_config`, `markdownlint`, full suite) with their output | `final-validation.md` |
| T2, T4 | the red→green transition of the two regression tests, quoted from the run | `final-validation.md` |
| T9 | the abuse rows and where each is asserted | `security-review.md` |
| T15 | recorded as operator-run, with the exact procedure | `final-validation.md` |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_modelchoice.py`
- [x] T2, T3, T4, T6, T9 — `uv run --project cli python -m pytest -q cli/tests/test_spawn_gate_integration.py`
- [x] T5, T6 — `uv run --project cli python -m pytest -q cli/tests/test_dispatcher_choice.py`
- [x] T7 — `uv run --project cli python -m pytest -q cli/tests/test_standing.py cli/tests/test_standing_integration.py`
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests/test_models_cmd.py`
- [x] T10 — `uv run --project cli python -m pytest -q cli`
- [x] T11 — `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py`
- [ ] T15 — operator-run on a devbox (not reproducible in this session; see
      `evidence/final-validation.md` for the procedure)

## Verification results

Executed 2026-09-18 in the work item's own checkout; the full record with the red→green
transition and the gate output is `evidence/final-validation.md`.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_modelchoice.py` | pass — 39 tests | `evidence/final-validation.md` T1 |
| T2, T3, T4, T6, T9 | `uv run --project cli python -m pytest -q cli/tests/test_spawn_gate_integration.py` | pass — 8 tests (4 new, red before the fix) | `evidence/final-validation.md` T2–T4, T6, T9 |
| T5, T6 | `uv run --project cli python -m pytest -q cli/tests/test_dispatcher_choice.py` | pass — 25 tests (3 new, 2 red before the fix; the 22 issue-358 tests run against the rewired fixture) | `evidence/final-validation.md` T5, T6 |
| T7 | `uv run --project cli python -m pytest -q cli/tests/test_standing.py cli/tests/test_standing_integration.py` | pass — 84 tests (2 new, red before the fix) | `evidence/final-validation.md` T7 |
| T8 | `uv run --project cli python -m pytest -q cli/tests/test_models_cmd.py` | pass — 9 tests (1 new, red before the fix) | `evidence/final-validation.md` T8 |
| T10 | `uv run --project cli python -m pytest -q cli` | pass — 3896 passed, 1 skipped | `evidence/final-validation.md` § Gates |
| T11 | `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py cli/tests/test_api_contract_parity.py cli/tests/test_routing.py cli/tests/test_eventlog_integration.py` | pass — 211 tests | `evidence/final-validation.md` T11 |
| T15 | the report's own procedure on a devbox | **not run** — operator-run; no `tmux`, harness binary or live work item here | `evidence/final-validation.md` T15 |
