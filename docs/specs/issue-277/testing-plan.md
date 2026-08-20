---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#277"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: sessions that outlive every work item

> Derived from the approved `requirements.md` and `design.md`, **before** `tasks.md`.
> Authored at `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the config parser's every refusal, the record store's round-trip and failure modes, the ref grammar, the tmux-name derivation, and — the check that the refactor is one — that a work-item spawn/deliver/kill still issues the identical tmux argv | `make test` (`cli/tests/test_standing.py`, `cli/tests/test_tmux_runner.py`) |
| T2 | Integration (scenario) | yes | the four behaviours that *are* the feature: start → stop → start resumes the same conversation; `the-loop start/stop/status` carry the sessions; a Slack thread reply reaches the pane and touches no ticket; a live unaccounted-for tmux session is refused | `make test` (`cli/tests/test_standing_integration.py`, `cli/tests/test_standing_channels_integration.py`) |
| T3 | Contract (OpenAPI) | yes | the served app's schema equals the authored `docs/api-specs/openapi/the-loop.v1.yaml` for the four new operations | `make test` (`cli/tests/test_api_contract_parity.py`, unchanged test, new contract) |
| T4 | End-to-end | n/a — an E2E would need a real tmux server, a real `claude` binary and a real Slack workspace. The tmux seam is faked at `TmuxRunner` (as every other session test in this repo fakes it) and the Slack seam at `client_factory`, which the existing `test_reactions_integration`/`test_interaction_integration` precedent already establishes as the boundary worth testing to. | | |
| T5 | UI / visual | n/a — no UI surface changes. The dashboard reads `/api/v1`; rendering a standing-sessions panel is not in this work item. | | |
| T6 | Snapshot | n/a — no rendered artifact is asserted verbatim. | | |
| T7 | Performance / load | n/a — the work is one subprocess per session at start; nothing is on a request path. | | |
| T8 | Security / abuse case | yes | one negative test per trust boundary in `design.md` §Security considerations: a `standing:` string cannot address a work-item verb and a work-item ref cannot address a standing one; an unauthorized Slack member is dropped before either standing branch runs; `say` into a stopped session refuses instead of spawning; a `cwd` that does not exist is refused | `make test` (`cli/tests/test_standing_security_integration.py`) |
| T9 | Accessibility | n/a — no UI. | | |
| T10 | Migration / upgrade | yes | a CLI config with no `standingSessions` block loads, validates and behaves exactly as before; `the-loop migrate-config` needs no new step | `make test` + `make validate` |
| T11 | Manual exploratory | n/a — every surface is covered above and the harness/tmux seams are not manually reachable in CI. | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.2, R1.3, R1.5 | a bad name, a duplicate name, both prompt sources — each refused with the offending entry named |
| T1 | R1.4 | harness/args/cwd inherited from `routing` when the entry omits them |
| T1 | R2.7 | a stopped record keeps its conversation id |
| T1 | R3.1 | `parse_standing_ref` accepts only `standing:<valid-name>` |
| T1 | (D2) | `spawn`/`deliver`/`kill`/`terminate_harness` for a work item issue the same argv after the split as before it |
| T2 | R2.3, R2.4, R2.6, R2.7 | `Scenario: a stopped standing session is resumed, not restarted from nothing` |
| T2 | R2.1, R2.2, R2.5, R2.8 | `Scenario: the-loop start, stop and status carry the standing sessions` |
| T2 | R4.1, R4.2, R4.3 | `Scenario: a Slack thread reply reaches a standing session and no ticket` |
| T2 | R2.9 | `Scenario: a live tmux session the-loop cannot account for is never spawned over` |
| T1 | R6.1, R6.7 | a record round-trips its whole definition, and reads back as a declaration |
| T1 | (compat) | a record written before the create verb still auto-starts; a hand-edited `harnessArgs` that is not a list is ignored |
| T2 | R6.1, R6.7 | `Scenario: a standing session is created through the API, with no config entry` |
| T2 | R6.4 | `Scenario: a created standing session is deleted and does not come back` |
| T2 | R6.6 | `Scenario: the-loop restart does not destroy the sessions the API created` |
| T8 | R6.2 | a create for a name already declared, or already recorded, is refused |
| T8 | R6.5 | a delete of a **declared** session is refused, naming the config key |
| T8 | R6.3 | a created session's bad name, missing `cwd` or failed start never leaves a half-session |
| T8 | R3.1 | a created session is not addressable as a work item either |
| T2 | R5.1, R5.2 | `Scenario: a standing session is told what it is not` — the directive precedes the operator's prompt in the pasted argv |
| T3 | R3.5, R6 | the **six** REST operations appear in the served schema exactly as authored |
| T8 | R3.1, R3.2 | `Scenario: the two session namespaces cannot address each other` |
| T8 | R4.4 | `Scenario: an unauthorized Slack member never reaches a standing session` |
| T8 | R3.4 | `Scenario: a message into a stopped standing session refuses instead of spawning one` |
| T8 | (design §Error handling) | a `cwd` that does not exist is refused before any spawn |
| T10 | R1.1 | a config with no `standingSessions` block is unchanged in every observable way |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. tmux is faked at the `TmuxRunner` seam and Slack at
  `SlackBotChannel`'s `client_factory`; no real tmux server, harness binary or Slack
  workspace is contacted.
- **Fixtures & data:** `tmp_path`-scoped CLI configs and state roots, as every other
  session test in `cli/tests/` uses.
- **Credentials:** none. The Slack tests never read a token — the injected client factory
  is reached before `_client()` needs one, and the token env var names travel by
  reference (`channels.slack.botTokenEnv`) as they already do.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T10 | full `make test` summary, before and after | `tests.md` |
| T1, T2, T8 | the new tests' own run, with the scenario titles | `scenarios.md` |
| T3 | the contract-parity assertion's run | `tests.md` |
| all | `make lint`, `make format-check`, `pyright cli`, `make validate` | `checks.md` |

## Verification activities

- [x] T1/T2/T8/T10 — `make test`
- [x] T1/T2/T8 — `uv run --project cli python -m pytest -q cli/tests/test_standing.py cli/tests/test_standing_integration.py cli/tests/test_standing_channels_integration.py cli/tests/test_standing_security_integration.py`
- [x] T3 — `uv run --project cli python -m pytest -q cli/tests/test_api_contract_parity.py`
- [x] T10 — `make validate`
- [x] all — `make lint && make format-check && uv run pyright cli`

## Verification results

Every activity ran, first time, on 2026-08-20. Nothing was replanned and nothing was
skipped.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1/T2/T8/T10 | `make test` | **2600 passed, 1 skipped** (2501 passed, 1 skipped on `main` at `b6bfda1` — +99, none removed) | [tests.md](evidence/tests.md) |
| T1/T2/T8 | the four new test files alone | **96 passed** (the other 3 of the +99 are the runner-split tests, below) | [tests.md](evidence/tests.md) |
| T1 | `pytest cli/tests/test_tmux_runner.py` | **114 passed** (111 before; the 111 unchanged — the check that the runner split is a refactor) | [tests.md](evidence/tests.md) |
| T2/T8 | `the-loop scenarios` over the new integration files | **11 scenarios** indexed, each naming the requirements it proves | [scenarios.md](evidence/scenarios.md) |
| T3 | `pytest cli/tests/test_api_contract_parity.py` | **2 passed** — the served schema equals the authored contract, including the four new operations | [tests.md](evidence/tests.md) |
| T10 | `make validate` | **VALID** for this repository's config, the shipped template and both schemas | [checks.md](evidence/checks.md) |
| T10 | the parity gates (docs, SDK docs, state, event catalog, schema) | **62 passed** | [tests.md](evidence/tests.md) |
| all | `make lint`, `make format-check`, `uv run pyright cli`, markdownlint | clean, first run | [checks.md](evidence/checks.md) |

**Not executed:** none.

**Re-verified on 2026-08-20 after the owner's ruling** ([decision-100](../../decisions/decision-100.md))
added `create`/`delete` and withdrew the control-plane-as-channel alternative. Every
activity ran again; the counts above are the second run.

One thing the verification *changed* about the plan, recorded rather than quietly done:
`test_configschema.py`'s keyword guard failed as soon as the schema used `pattern`, which
the hand-written validator did not implement. `pattern` is now implemented (as an
unanchored `re.search`, which is what JSON Schema means and what the differential test
against real `jsonschema` requires) and added to `SUPPORTED`/`CONSTRAINING`. That is
in-scope work the plan did not anticipate, not a matrix change: the name constraint is
load-bearing (the value becomes a tmux target and a file name), so validating it was never
optional.

## Review comments

*None yet.*
