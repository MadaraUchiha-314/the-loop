---
type: testing-plan
phase: test-planning
workItem: issue-163
status: approved
approvedBy: []
overrides: {}
---

# Testing plan: test and verification as nodes in the PDLC

> Derived from the approved [`requirements.md`](requirements.md) and
> [`design.md`](design.md), before [`tasks.md`](tasks.md). Authored at `test-planning`,
> completed at `verification`. This work item dogfoods the artifact it introduces.
>
> **This file is executable content** — it names commands an agent will run. Credentials
> appear by reference only; there are none to name here.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the shipped graph declares both nodes with their phases, edges and gate params; a `skip` no longer short-circuits a chain | `uv run pytest cli/tests/test_graph_model.py cli/tests/test_graph_chain.py` |
| T2 | Integration (scenario) | yes | the real hook chain over a temporary spec folder: planning blocks unlocked/short plans, verification blocks unticked activities, `implementation` reaches `verification` | `uv run pytest cli/tests/test_graph_verification_integration.py` |
| T3 | Contract (structural parity) | yes | graph ↔ manifest ↔ template ↔ config agreement (P1–P4): the new artifact is tracked at its phase, gated, template-satisfiable, and both configs declare the phases in graph order | `uv run pytest cli/tests/test_graph_parity.py` |
| T4 | Schema validation | yes | both harness configs still validate after the phases/stages change | `make validate` |
| T5 | Lint / typecheck / format | yes | ruff, pyright, markdownlint over the whole tree — most of this change is markdown, so the markdown lint *is* a functional test here | `make lint`, `make typecheck`, `make format-check` |
| T6 | Regression (full suite) | yes | the chain-semantics change touches every node evaluation in the product; the whole suite is the blast-radius check | `make test` |
| T7 | Contract (OpenAPI / GraphQL) | n/a — the control-plane API is untouched; no route, schema or client changes | | |
| T8 | End-to-end | n/a — the change is declarative (graph, schema, manifest, templates, prose). T2 drives the real runtime and hooks, which is the furthest end-to-end this has | | |
| T9 | UI / visual | n/a — the-loop ships a CLI, a plugin and docs; this work item adds no user-facing surface (`design.md` §UI/UX is N/A) | | |
| T10 | Snapshot | n/a — no serialized output is introduced; `graph show --format json` gains two nodes, covered structurally by T1/T3 rather than by a golden file that would need updating on every graph edit | | |
| T11 | Performance / load | n/a — two extra nodes are two extra file reads at gate-evaluation time; no hot path, no budget to hold | | |
| T12 | Security / abuse case | yes | the boundaries this touches are enforced by *review*, not by code (see below) — the one structural claim is that no gate was weakened, which T1 asserts | `uv run pytest cli/tests/test_graph_model.py -k Testing` |
| T13 | Accessibility | n/a — no UI | | |
| T14 | Migration / upgrade | yes (analysis, not a test run) | an in-flight work item with no `testing-plan.md` blocks at `test-planning` — the intended fail-closed behaviour, with `the-loop graph force` as the audited escape hatch. Recorded in `design.md` §Error handling; no data or config migration is introduced | reviewed |
| T15 | Manual exploratory | n/a — there is no interactive surface to explore; the gate behaviour is fully covered by T2 | | |

**On T12.** `design.md` §Security design is explicit that this work item's security
controls — evidence redaction, credentials-by-reference, treating a plan as executable
content — are **review-enforced conventions written into the template**, not code. There
is no mechanism to test, and asserting a rule against its own prose would be a test that
can only pass. Automating redaction is named as out of scope in `requirements.md`. The one
testable security claim is structural and *is* tested: no existing gate was weakened —
`security-review` stays `required: true`, the six post-implementation nodes still exist,
and `verification` sits before the review chain.

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R3.1, R3.2, R6.1 | `TestTestingIsPlannedAndVerifiedAsNodes` (5 cases); `TestASkipIsNotADecision` (3 cases) |
| T2 | R1.1, R1.2, R1.4, R3.1, R3.2, R3.3 | `Scenario: the test-planning node will not pass without a locked plan` · `…a locked plan carrying the gated sections clears the planning node` · `…the results heading must be authored holding something` · `…an activity that was planned but not executed keeps the gate shut` · `…an executed plan with recorded results clears the verification node` · `…the implementation node routes to verification on a pass` · `…the template an agent authors from can pass its own gate` |
| T3 | R1.4, R6.1, R6.2 | P1–P4 in `test_graph_parity.py` |
| T4 | R6.1, R6.4 | `scripts/validate_config.py` over both harness configs |
| T5 | R6.3 | markdownlint over 406 files; ruff + pyright over `cli`/`hooks` |
| T6 | all | 1326 tests |
| T12 | R-sec (abuse case 4) | `test_the_verification_gate_is_not_a_silent_skip`, `test_the_shipped_graph_splits_the_needs_review_label` |

## Verification environment

This repository only — no second checkout, no service, no fixture data, no credentials.

- **Repositories:** this one.
- **Services / containers:** none.
- **Fixtures & data:** none; T2 builds its spec folder in `tmp_path`.
- **Credentials:** none. (Nothing here reaches a network; `Runtime.evaluate` is pure by
  contract — no network, no subprocess, no mutation.)
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T3, T6 | test run summaries (full suite + the four graph suites) | `unit-and-integration.txt` |
| T4, T5 | lint, typecheck, format and schema-validation output | `lint-typecheck-validate.txt` |
| T2 | the scenario rows this work item adds, from `the-loop scenarios --format markdown` | `scenarios.md` |

Nothing captured here touches a credential, a hostname or personal data — the commands are
local test runners over this repository — so no redaction was required.

## Verification activities

- [x] T1 — `uv run pytest cli/tests/test_graph_model.py cli/tests/test_graph_chain.py`
- [x] T2 — `uv run pytest cli/tests/test_graph_verification_integration.py`
- [x] T3 — `uv run pytest cli/tests/test_graph_parity.py`
- [x] T4 — `make validate`
- [x] T5 — `make lint && make typecheck && make format-check`
- [x] T6 — `make test`
- [x] T12 — `uv run pytest cli/tests/test_graph_model.py -k Testing`
- [x] T14 — reviewed: in-flight items block at `test-planning`; escape hatch recorded

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|---------------------|---------|----------|
| T1 | `uv run pytest cli/tests/test_graph_model.py cli/tests/test_graph_chain.py` | pass | [unit-and-integration.txt](evidence/unit-and-integration.txt) |
| T2 | `uv run pytest cli/tests/test_graph_verification_integration.py` | pass — 7 scenarios | [unit-and-integration.txt](evidence/unit-and-integration.txt), [scenarios.md](evidence/scenarios.md) |
| T3 | `uv run pytest cli/tests/test_graph_parity.py` | pass — P1–P4 | [unit-and-integration.txt](evidence/unit-and-integration.txt) |
| T4 | `make validate` | pass — 6 config files VALID | [lint-typecheck-validate.txt](evidence/lint-typecheck-validate.txt) |
| T5 | `make lint`, `make typecheck`, `make format-check` | pass — ruff clean, markdownlint 0 errors over 406 files, pyright 0 errors, 165 files formatted | [lint-typecheck-validate.txt](evidence/lint-typecheck-validate.txt) |
| T6 | `make test` | pass — **1326 passed, 1 skipped** (1322 before this work item; +4 net from the new suites and cases) | [unit-and-integration.txt](evidence/unit-and-integration.txt) |
| T12 | `uv run pytest cli/tests/test_graph_model.py -k Testing` | pass — the verification gate declares `produces` and is not a skip; no existing gate weakened | [unit-and-integration.txt](evidence/unit-and-integration.txt) |
| T14 | Reviewed the upgrade path for work items whose spec folder predates this change | blocks at `test-planning` as designed; `the-loop graph force --to <node> --reason <why>` is the audited override, and it never forges the verdict | [design.md §Error handling](design.md) |

**Not executed:** none. Every planned activity ran.

**Found during verification, not planned:** T6 surfaced nothing, but writing T2 surfaced a
real defect outside the original matrix — `run_chain` short-circuited on `skip`, so
`implementation` (whose chain ends in a skipping `verify-tests`) routed on the outcome
`"skip"`, for which no edge exists, and parked at `no_edge` rather than advancing. The
`implementation → verification` edge this work item introduces would have been
unreachable. Fixed, and covered by `TestASkipIsNotADecision` under T1; recorded in
[decision-060](../../decisions/decision-060.md).

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
