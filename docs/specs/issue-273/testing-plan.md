---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#273"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: prove the gate runs, and that nothing else moved

> Derived from the approved `bugfix.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the exempt actions (`start`, `context`) and the gated ones (`advance`, `clean`); no `graph.skipped` for an exempt action; the skip record still names a gated one; declared-`specDir` parity across both; the `pending` context and its rendered block | `make test` (`uv run pytest cli/tests`) |
| T2 | Integration (scenario) | yes | the ticket's reproduction end to end against a **real** `Dispatcher` and a real `graph.Runtime` over the shipped `pdlc-work-item-loop`: a plain ticket is held at `phase-selection`, labelled, and asked. Gherkin-documented | `make test` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — the control-plane API is untouched: no path, schema or response shape changes, and `GraphContext` is not exposed through it | | |
| T4 | End-to-end | n/a — a real run needs a GitHub repository, a `gh` credential and a real tmux/harness. T2 drives the real dispatcher and the real runtime against injected fakes, which is how this seam has always been proved in this repo | | |
| T5 | UI / visual | n/a — no user-facing surface | | |
| T6 | Snapshot | n/a — no rendered artefact changes. The two prompt **templates** are deliberately untouched (design § Trade-offs), so the byte-identical parity test in `test_interaction.py` is a guard that they stayed that way, not a test of this change | | |
| T7 | Performance / load | n/a — one membership test removed from a per-delivery path, and one extra graph read on a path that already builds the runtime. Nothing measurable above noise | | |
| T8 | Security / abuse case | yes | the authorization tail: an unauthorized `the-loop execute` on the freshly started graph moves nothing; an unarmed work item is still refused before the predicate is reached; a foreign checkout is still refused | `make test` |
| T9 | Accessibility | n/a — no user interface | | |
| T10 | Migration / upgrade | yes | a deployment already carrying work items **with** spec folders is unchanged: their graphs start, advance and report exactly as before, and a started graph never reports `pending` | `make test` |
| T11 | Manual exploratory | n/a — the reproduction is a spawn against a real dispatcher; mechanised as T2, which is stricter (it asserts the graph state and the posted checklist, not the observed symptom) | | |
| T12 | Static analysis (lint + types) | yes | `ruff`, `pyright`, `markdownlint` over the changed modules and docs | `make lint` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1 | `test_a_work_item_with_no_spec_directory_is_still_started` — the start reaches the runtime |
| T1 | R1.1 | `test_a_start_with_no_spec_directory_records_no_skip` — neither `context` nor `start` records `graph.skipped` |
| T1 | R1.4 | `test_an_advance_still_requires_the_spec_directory` — the runtime is never reached |
| T1 | R1.4 | `test_a_skipped_work_item_is_recorded_in_the_event_log` / `test_the_skip_record_names_the_action_that_was_refused` — the record survives, naming `advance` |
| T1 | R1.4 | `test_link_a_work_item_with_no_spec_directory_is_a_no_op` (issue-186's, unchanged) — `clean` still skips |
| T1 | R1.5 | `test_the_gate_reads_the_same_directory_the_runtime_will` — the stale `docs/specs` does not satisfy the gated action, and the exempt one builds its runtime on the declared `specs` |
| T1 | R2.1, R2.3 | `test_a_fresh_item_reports_the_node_it_is_about_to_stand_on` — the start node, `pending`, and not a human gate |
| T1 | R1.2 | `test_a_repository_is_adopted_even_when_its_graph_is_skipped` — adoption still precedes the start, and `graph-state.json` now lands |
| T2 | R1.1, R1.2 | `Scenario: A work item minted as a plain ticket starts at the human gate` — pointer at `phase-selection`, `loop:phase-selection` set, one checklist posted asking for `the-loop execute`, no `graph.skipped` |
| T2 | R2.1, R2.2, R2.5 | `Scenario: The prompt is rendered before the graph is entered` — the block names the node, says NOT ENTERED YET, names the human gate, and carries no claim line |
| T8 | R1.3 | `Scenario: Starting the graph is not the same as walking it` — an unauthorized `the-loop execute` leaves the pointer at `phase-selection` |
| T8 | R1.6 | the existing refusal suite in `test_graphlink.py` (disabled link, non-GitHub ref, unstarted item, foreign checkout, escaping `specDir`) — all unchanged and still green |
| T10 | R2.3 | `Scenario: pending never masks a work item in flight` — a started graph reports its real node and a status that is not `pending` |
| T10 | R2.6 | `test_a_disabled_link_does_nothing` and the foreign-checkout tests — no context, so an empty block, so an unchanged prompt |
| T12 | R4 | lint and type checks pass over the changed modules and docs |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. No tmux, no harness, no network: the graph's outbound
  integration is replaced at `the_loop.graph.integrations.resolve` (the seam issue-194
  established), and the checkouts are real `git init` trees under `tmp_path`.
- **Fixtures & data:** the existing `test_graphlink*.py` fixtures plus a `_bare_checkout`
  helper (a real checkout with **no** spec folder — the shape of the bug) and a `_FakeGitHub`
  recording the label and the checklist.
- **Credentials:** none.
- **Bring-up:** `make test` · **Tear-down:** none (pytest `tmp_path`).
- **If bring-up fails:** record it under Verification results, leave the dependent activities
  unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T10 | red run — the new and rewritten tests, run before any production code changed | `red.md` |
| T1, T2, T8, T10 | green run — full suite summary and the per-file runs | `unit-and-integration.md` |
| T12 | `make lint` / type-check output | `lint-and-typecheck.md` |
| — | security review record (checklist per `reference/security.md`) | `security-review.md` |

## Verification activities

- [x] T1 — `uv run pytest -q cli/tests/test_graphlink.py cli/tests/test_graph_drive.py`
- [x] T2, T8, T10 — `uv run pytest -q cli/tests/test_graphlink_integration.py cli/tests/test_harness_config_scaffold_integration.py`
- [x] T12 — `make lint` (`ruff check`, `ruff format --check`, `markdownlint-cli2`) and `make typecheck`
- [x] Full suite — `make test`
- [x] Red run captured before the fix — `evidence/red.md`
- [x] Security review — the checklist in `reference/security.md`, against the diff

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|---|---|---|---|
| Red run | the 8 new/rewritten tests, run with the production change stashed | 8 failed, 79 passed — every one of them failing on the behaviour, not on a missing symbol | [`evidence/red.md`](evidence/red.md) |
| T1 | `pytest -q cli/tests/test_graphlink.py cli/tests/test_graph_drive.py` | 63 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T2, T8, T10 | `pytest -q cli/tests/test_graphlink_integration.py cli/tests/test_harness_config_scaffold_integration.py` | 24 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| Full suite | `make test` | **2477 passed, 1 skipped** | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T12 | `uv run ruff check`, `uv run ruff format --check`, `uv run pyright cli`, `markdownlint-cli2` | clean | [`evidence/lint-and-typecheck.md`](evidence/lint-and-typecheck.md) |
| Security review | checklist (`reference/security.md`), effective risk tier 3 | pass, no unresolved findings | [`evidence/security-review.md`](evidence/security-review.md) |

Every planned activity ran. Nothing was replanned, and nothing is left unticked.
