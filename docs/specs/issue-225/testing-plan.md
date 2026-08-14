---
type: testing-plan
phase: test-planning
workItem: "issue-225"
status: approved
approvedBy: []
overrides: {}
---

# Testing plan: ad-hoc tasks that run no PDLC process

> Derived from the approved `requirements.md` and `design.md`, **before** `tasks.md`.
> Authored at `test-planning` and completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the graph compiles with the specified shape and gates nothing; `classify-adhoc-reply`'s three outcomes; the `do` keyword's parsing, arming and spawn-arming; `resolve_outer_loop`'s fail-closed set; `LOOP_FOR_CONTROL_COMMAND`'s keys are real control commands | `uv run --project cli pytest cli/tests/test_graph_adhoc.py` |
| T2 | Integration (scenario) | yes | the whole walk against the stub GitHub integration — `work → review → (more-work) → work → review → (done) → complete` — with Gherkin docstrings | `uv run --project cli pytest cli/tests/test_graph_adhoc.py -k Walk` |
| T3 | Contract (OpenAPI / GraphQL SDL) | yes | the control-plane contract is unchanged by this work item — no route, request or response shape is added; `test_api_contract_parity` proves it | `uv run --project cli pytest cli/tests/test_api_contract_parity.py` |
| T4 | End-to-end | n/a — the-loop's e2e harness (`cli/tests/test_pdlc_e2e/`) drives scenarios against a mocked agent for the **outer** loop's phase chain; the ad-hoc loop has no phase chain to drive, and T2 already exercises every node and edge it has | | |
| T5 | UI / visual | n/a — no user-facing UI surface; the Control Plane UI is not touched | | |
| T6 | Snapshot | n/a — no snapshot-tested output in this change | | |
| T7 | Performance / load | n/a — one more YAML compiled at load, one more tuple membership test per resolution; no hot path | | |
| T8 | Security / abuse case | yes | one negative test per abuse case in `requirements.md` §Security considerations: unauthorized arming, two-command refusal, self-authored "done", invented loop name, unauthorized reply at the gate | `uv run --project cli pytest cli/tests/test_graph_adhoc.py -k "unauthorized or refused or invented or self_authored"` |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | yes | a pre-issue-225 `graph-state.json` (no `loop`, or `loop: pdlc-contribution-loop`) still resolves exactly as before; the three generalized call sites are behaviour-preserving for the existing loops | `uv run --project cli pytest cli/tests/test_graph_contribution.py cli/tests/test_graphlink.py cli/tests/test_core_graphs.py` |
| T11 | Manual exploratory | n/a — every surface is a library call or a config leaf, and the parity tests cover the docs/schema pairing mechanically | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1–R1.6 | the shipped graph compiles; three walkable nodes plus two terminals; no `produces`; no `validate-artifacts`; no `skipSets`; no node `required` or `skippable`; a repo-supplied override is warned about |
| T1 | R2.1, R2.3 | `do` is in `COMMANDS`, `SPAWN_COMMANDS` and the arming set; `DEFAULT_KEYWORDS[do] == "the-loop do"` |
| T1 | R2.4 | `resolve_outer_loop` returns `""` for an invented name, for `pdlc-pr-loop`, and for the default |
| T1 | R3.1–R3.4 | `classify-adhoc-reply` → `waiting` / `done` / `more-work`; newest authorized comment decides |
| T2 | R3.1–R3.3, R4.2 | `Scenario: an ad-hoc item walks work → review → work → complete on its requester's replies` |
| T2 | R2.5 | `Scenario: the core verbs address an ad-hoc item through its recorded loop` |
| T3 | R1.1 | the control-plane API contract is unchanged |
| T8 | R2.1 abuse 1 | `Scenario: an unauthorized "the-loop do" arms nothing` |
| T8 | abuse 2 | `Scenario: a comment carrying two control keywords is refused` |
| T8 | abuse 3 | `Scenario: the harness cannot end its own ad-hoc work item` |
| T8 | abuse 4 | `Scenario: an invented loop name in agent-writable state selects no graph` |
| T8 | abuse 5 | `Scenario: an unauthorized reply leaves the ad-hoc gate open` |
| T10 | R5.2 | the contribution and outer loops behave identically after the generalization |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. Every test is an in-process filesystem test against
  `tmp_path`; the GitHub integration is the suite's existing stub.
- **Fixtures & data:** `cli/tests/conftest.py` and the fakes in `test_graph_adhoc.py`.
- **Credentials:** none — no test touches the network.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8 | the new suite's run output (counts, duration, scenario names) | `unit-and-integration.md` |
| T3, T10 | the full suite's run output, proving nothing else moved | `full-suite.md` |
| — | `ruff`, `pyright` and `markdownlint` output | `lint-and-types.md` |

## Verification activities

> Run from `cli/`, so `pytest`'s configured `testpaths` apply.

- [x] T1 — `uv run pytest tests/test_graph_adhoc.py`
- [x] T2 — `uv run pytest tests/test_graph_adhoc.py -k Walk`
- [x] T3 — `uv run pytest tests/test_api_contract_parity.py`
- [x] T8 — `uv run pytest tests/test_graph_adhoc.py -k "unauthorized or refused or
  invented or self_authored or empty_allowlist or prose"`
- [x] T10 — `uv run pytest tests/test_graph_contribution.py tests/test_graphlink.py
  tests/test_core_graphs.py`, plus `uv run pytest` for the whole suite and its parity
  tests
- [x] lint / types — `uv run ruff check cli hooks`, `uv run ruff format --check cli
  hooks`, `uv run pyright cli`, `markdownlint-cli2`, `scripts/validate_config.py`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 + T2 + T8 | `uv run pytest tests/test_graph_adhoc.py` (from `cli/`) | pass — 57 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T3 | `uv run pytest tests/test_api_contract_parity.py` | pass — 1 passed | [`evidence/full-suite.md`](evidence/full-suite.md) |
| T10 | `uv run pytest tests/test_graph_contribution.py tests/test_graphlink.py tests/test_core_graphs.py` | pass — 98 passed | [`evidence/full-suite.md`](evidence/full-suite.md) |
| whole suite | `uv run pytest` | pass — 2023 passed, 1 skipped | [`evidence/full-suite.md`](evidence/full-suite.md) |
| lint / types | `uv run ruff check .` · `uv run ruff format --check .` · `uv run pyright` · `markdownlint-cli2` | pass | [`evidence/lint-and-types.md`](evidence/lint-and-types.md) |

**Not executed:** none.

## Review comments
