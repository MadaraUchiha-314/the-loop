---
type: testing-plan
phase: test-planning
workItem: issue-188
status: approved              # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: an opt-in critic review of the locked design

> Derived from the approved `requirements.md` and `design.md`. Authored at
> `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | compile-time vocabulary (`optIn` parsed, `required`×`optIn` refused, an opt-in `skipSets` member refused, the implied `skippable` edge requirement), checklist rendering, reply parsing (ticked / unticked / absent), the runtime default, the *not selected* provenance line, state round-trip | `uv run pytest cli/tests/test_graph_skips.py cli/tests/test_graph_model.py cli/tests/test_graph_state.py` |
| T2 | Integration (scenario) | yes | a work item walking the miniature loop end to end **both ways** — selected (the node is entered and gates its section) and not selected (the pointer routes `design → test-planning` with no hooks run), plus the shipped outer loop's own shape | `uv run pytest cli/tests/test_graph_skips.py -k opt_in` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — the control-plane API gains no endpoint and no field; `optIns` lives in `graph-state.json`, which the contract does not describe | | |
| T4 | End-to-end | n/a — an end-to-end run needs a live GitHub ticket, an authorized human and a configured critic CLI; the seams that stand in for them (the github integration, `_authorized_comments`, the critic runner) are covered at T2 and already have their own suites | | |
| T5 | UI / visual | n/a — no user-facing surface; the only rendered output is a markdown comment, asserted as text at T1 | | |
| T6 | Snapshot | n/a — the checklist body is asserted by content, not by golden file; a snapshot would lock wording the writing skill expects to evolve | | |
| T7 | Performance / load | n/a — one extra dict comprehension over a ~20-node graph per read | | |
| T8 | Security / abuse case | yes | the three testable abuse cases in `design.md` §Security design: unauthorized reply ignored, forged `optIns` on a non-opt-in node inert, a deleted selection reverting to *not selected* (never `pass`) | `uv run pytest cli/tests/test_graph_skips.py -k "forged_opt_in or deleting_a_selection or unauthorized_reply_never_selects_an_opt_in"` |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | yes | a pre-issue-188 `graph-state.json` (no `optIns` key) loads, defaults to no selection, and leaves an in-flight work item unblocked | `uv run pytest cli/tests/test_graph_state.py -k "opt_ins or without_opt_ins"` |
| T11 | Manual exploratory | yes | `the-loop check` on this repository's own `docs/specs/issue-188/`, reading the new node's line in the report | `uv run the-loop check issue-188` |
| T12 | Parity (docs ↔ graph ↔ templates) | yes | the gated `Design critic review` section exists in the shipped `execution-log.md` template (P5c) and the phase sequence still matches both configs (P4) | `uv run pytest cli/tests/test_graph_parity.py cli/tests/test_docs_parity.py cli/tests/test_writing_parity.py` |
| T13 | Lint / type check | yes | `ruff`, `pyright`, `markdownlint` over the changed Python and markdown | `make lint typecheck` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.2, R1.3 | `optIn` compiles, implies `skippable`; `required`×`optIn` and an opt-in skip-set member both raise `GraphConfigError` |
| T1 | R1.4, R1.5 | an unselected opt-in node reports `skip` with *not selected*, in both `check` modes |
| T1 | R2.1, R2.2 | the checklist renders opt-in rows unticked, under their own heading, with the node's `description` |
| T1 | R2.3, R2.4 | ticked → selected; unticked → not selected; absent → not selected |
| T1 | R2.5, R2.6 | the confirmation names selected opt-in phases, or says none were; an untouched selection still runs every default-on phase |
| T2 | R3.1, R3.2 | `Scenario: a work item that selects the design critic round walks it between design and test-planning` |
| T2 | R3.2 | `Scenario: a work item that does not select it routes design straight to test-planning, running none of the node's hooks` |
| T2 | R3.3 | `Scenario: the design critic node blocks until the execution log's Design critic review section is written` |
| T2 | R3.6 | the inner PR loop and the contribution loop declare no opt-in node |
| T2 | R1.6, R1.8 | a selection is recorded with provenance and frozen into the graph record carrying `optIn` per node |
| T8 | R1.7, security AC 1–3 | unauthorized reply ignored; forged/removed `optIns` inert |
| T10 | NFR backward compatibility | a state file without `optIns` loads and selects nothing |
| T12 | R3.3 | the gated section exists in the template |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. Every test is a filesystem/in-process read; the github
  integration is stubbed, as it is throughout `cli/tests`.
- **Fixtures & data:** the miniature graph dict already in `cli/tests/test_graph_skips.py`,
  extended with one opt-in node; `tmp_path` spec folders.
- **Credentials:** none — no network call is made.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T10, T12 | pytest run output and counts | `tests.md` |
| T13 | lint + type-check output | `lint.md` |
| T11 | the `the-loop check` report showing the new node's line, both selected and not | `walkthrough.md` |

## Verification activities

- [x] T1 — `uv run pytest cli/tests/test_graph_skips.py cli/tests/test_graph_model.py cli/tests/test_graph_state.py`
- [x] T2 — `uv run pytest cli/tests/test_graph_skips.py -k opt_in`
- [x] T8 — `uv run pytest cli/tests/test_graph_skips.py -k "forged_opt_in or deleting_a_selection or unauthorized_reply_never_selects_an_opt_in"`
- [x] T10 — `uv run pytest cli/tests/test_graph_state.py -k "opt_ins or without_opt_ins"`
- [x] T11 — `uv run the-loop check issue-188`
- [x] T12 — `uv run pytest cli/tests/test_graph_parity.py cli/tests/test_docs_parity.py cli/tests/test_writing_parity.py`
- [x] T13 — `make lint typecheck`
- [x] Full suite — `uv run pytest cli/tests`

## Verification results

> Authored empty at `test-planning`, filled at `verification`. Counts are from the runs
> recorded in `evidence/`, not from this plan.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| Red→green | new tests run with the production change stashed, then restored | pass — 19 failed → 19 passed | [`evidence/tests.md`](evidence/tests.md) |
| T1 | `uv run pytest cli/tests/test_graph_skips.py cli/tests/test_graph_model.py cli/tests/test_graph_state.py` | pass — 116 passed | [`evidence/tests.md`](evidence/tests.md) |
| T2 | `uv run pytest cli/tests/test_graph_skips.py -k opt_in` | pass — 15 passed | [`evidence/tests.md`](evidence/tests.md) |
| T8 | `uv run pytest cli/tests/test_graph_skips.py -k "forged_opt_in or deleting_a_selection or unauthorized_reply_never_selects_an_opt_in"` | pass — 3 passed | [`evidence/tests.md`](evidence/tests.md) |
| T10 | `uv run pytest cli/tests/test_graph_state.py -k "opt_ins or without_opt_ins"` | pass — 2 passed | [`evidence/tests.md`](evidence/tests.md) |
| T11 | `the-loop graph show`, `the-loop check` on a scratch item with and without the selection, and on this work item | pass — reported *not selected* unselected, gated its section once selected | [`evidence/walkthrough.md`](evidence/walkthrough.md) |
| T12 | `uv run pytest cli/tests/test_graph_parity.py cli/tests/test_docs_parity.py cli/tests/test_writing_parity.py` | pass — 25 passed | [`evidence/tests.md`](evidence/tests.md) |
| T13 | `make lint format-check typecheck validate` | pass — ruff, markdownlint (501 files), pyright, schema validation all clean | [`evidence/lint.md`](evidence/lint.md) |
| Full suite | `uv run pytest cli/tests` | pass — 1650 passed, 1 skipped | [`evidence/tests.md`](evidence/tests.md) |

**Not executed:** T3–T7 and T9 — marked `n/a` in the matrix above with their reasons; none
was replanned or escalated. The one suite skip (`test_instructions.py:149`, an
unreadable-file case that cannot be staged as root) predates this change and is unrelated
to it. The fourth abuse case — a critic's output carrying instructions — is a documented
rule in `reference/reviewing.md` with no code path of its own, so it has no test row.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
