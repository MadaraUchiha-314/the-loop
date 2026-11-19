---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#543"
status: draft                # draft | in-review | approved — locked with design.md by the design-approval gate
approvedBy: []
overrides: {}
---

<!-- Written per the `the-loop:writing` skill. -->

# Testing plan: give each pull request of a multi-PR work item its own scoped spec

> Derived from the approved [requirements](requirements.md) and [design](design.md),
> before `tasks.md`. Authored at `test-planning` and completed at `verification`.
>
> **This file is executable content.** Review it like code. It names no credential: every
> GitHub call is stubbed.

## The short version

Most of the proof is unit and integration tests in the repository's own pytest suite.
They run against fixture trees: an origin checkout holding a chain and a work-item
state, and a PR checkout holding a PR spec. The GitHub client is stubbed, so visibility
and comments are deterministic and no token is needed. Five Gherkin scenarios carry the
end-to-end behaviour, and abuse cases AC1–AC5 each get a negative test. Two rows are
deliberately not automated:

- **A contract check** of the new OpenAPI path, through the repository's existing
  validation step.
- **A manual dogfood** run of the verb against this work item's own PR, which shows the
  record and the briefing link as a reviewer would meet them.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|---|---|---|---|
| T1 | Unit | yes | `pr-spec-current` hook: applicability (single-PR, multi-PR, `self` rows, declared repos, spec-only), record validation, digest recomputation with front matter stripped, stale detection, the forged-record cases; the verb's eight checks one by one; the citation parser and resolver for all five forms | `cd cli && uv run python -m pytest -q tests/test_pr_spec.py` |
| T2 | Integration (scenario) | yes | The five Gherkin scenarios in design § Testing strategy, driven through the real graph runtime and `the-loop graph` verbs | `cd cli && uv run python -m pytest -q tests/test_pr_spec_integration.py` |
| T3 | Contract (OpenAPI) | yes | `POST /api/v1/graph/pr-spec` exists in `the-loop.v1.yaml`, its request body carries the six fields, and the served schema matches the authored one (`test_api_contract_parity.py`) | `cd cli && uv run python -m pytest -q tests/test_api_contract_parity.py` |
| T4 | End-to-end | n/a | No live multi-repository GitHub fixture exists, and a run would need write access to two real repositories. T2 drives the same verbs and graph against stubbed GitHub; T11 shows the real artifacts on this repository. | |
| T5 | UI / visual | n/a | the-loop has no product UI. | |
| T6 | Snapshot | yes | The four `templates/pr-spec/*.md` templates and the rendered `pr-spec` assignment text, through the existing template-parity and assignment-render tests, extended to the new files | `cd cli && uv run python -m pytest -q tests/test_graph_loops.py tests/test_manifest_schemas.py tests/test_writing_parity.py` |
| T7 | Performance / load | n/a | The hook hashes four files and reads two JSON files per evaluation, in the same order of cost as `await-inner-loops`. There is nothing to load-test. | |
| T8 | Security / abuse case | yes | AC1 private→public refused without a grant, refused with an unauthorized or marked grant, refused with a grant naming another repository, and recorded with a valid one. AC2 a visibility fetch failure is refused as `visibility-unknown`. AC3 the verb's written-file set is exactly one `pr-spec.json` and the hook writes nothing. AC4 `..`, `/` and empty owner/repo/id parts, and a symlinked `docs/specs` escaping the checkout, are refused. AC5 a seeded token in a PR-spec file is a finding. A forged `required: false` record on a multi-PR item still blocks. | `cd cli && uv run python -m pytest -q tests/test_pr_spec.py -k "abuse or forged"` |
| T9 | Accessibility | n/a | No UI surface. | |
| T10 | Migration / upgrade | yes | Existing inner-loop states that sit at `implementation` or later and were written before `pr-spec` existed still load, and are not moved back to `pr-spec`. A work item with no `pr-spec.json` anywhere and a single PR passes every placement. `test_graph_skips.py` changes deliberately: `pr-spec` becomes the shipped inner loop's one skippable node. | `cd cli && uv run python -m pytest -q tests/test_graph_skips.py tests/test_graph_loops.py tests/test_graph_multirepo_integration.py` |
| T11 | Manual exploratory | yes | Dogfood on this repository. Write a PR spec for PR #546 at `docs/specs/issue-543/pr-546/`, run `the-loop graph pr-spec issue-543 --pr 546 --checkout .`, and record the output. Then edit `design.md` locally and show that `the-loop check issue-543 --pr 546` reports the record stale. The edit is discarded afterwards. | the commands named, from the repository root |
| T12 | Full suite and lint (CI parity) | yes | Nothing else regressed. Markdown lint covers the new templates, command and docs. | `make check` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1–R1.3, R1.6, R2.7, R3.1–R3.3, R3.5, R4.2, R4.4, R5.1 | applicability table; verb checks 1–8; citation forms; digest ignores front matter; no `status` key in a PR spec |
| T2 | R1.1, R4.1, R4.5 | `Scenario: a cross-repository PR cannot start implementation without a recorded PR spec` |
| T2 | R5.1, R5.2, R5.3 | `Scenario: a changed chain blocks the PR at reviewer-briefing until it is re-derived` (with the `--still-valid` path as a second example) |
| T2 | R1.2, NFR "single-repository unaffected" | `Scenario: a single-PR work item walks past pr-spec untouched` |
| T2 | R1.4, R1.6 | `Scenario: under never mode the outer implementation holds until every PR has a record` |
| T2 | Security AC1, AC2 | `Scenario: a private origin will not publish a PR spec to a public repository without an authorized grant` |
| T3 | Interfaces § API and schema | OpenAPI path and parity |
| T6 | R2.1–R2.6, R4.1, R4.6 | the templates' required sections and Context section; the assignment names both commands; the `pr-briefing.md` template links the PR spec first |
| T8 | Security AC1–AC5, forged record | negative tests listed in the matrix |
| T10 | R1.5, NFR "single-repository unaffected" | the skip declared via `graph skip --pr N --node pr-spec` reads *skipped by declaration*; pre-existing inner states load unchanged |
| T11 | R4.3, R4.6, R4.7, R5.1 | the real record, path and stale report on this repository |

R6 (feedback routing) and R7 (documentation) are session behaviour and text. No test runs
them. They are verified at review: R6 by reading `/the-loop:derive-pr-spec` and
`reference/workflow.md`, R7 by the `capability-docs` node's `evidence/documentation.md`.

## Verification environment

- **Repositories:** this repository only. The integration tests build a second "PR
  checkout" as a temporary git repository with a remote URL naming another repository,
  so no second real checkout is needed.
- **Services / containers:** none. Tests construct the graph runtime and the CLI
  in-process.
- **Fixtures & data:** fixture trees are created by the tests under `tmp_path`, and the
  GitHub client is stubbed per test. T11 uses this working tree.
- **Credentials:** none. T11's verb reads repository visibility through the service's
  GitHub client, which uses the operator's existing `GH_TOKEN`, by reference.
- **Bring-up:** `make install-dev` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T8, T10 | pytest summary per command (counts, duration, any failures) | `unit.md` |
| T2 | `the-loop scenarios --glob cli/tests/test_pr_spec_integration.py --format markdown`, then the run output | `integration.md` |
| T3, T6 | validate and parity output | `contract-and-snapshot.md` |
| T11 | the verb's JSON output, the committed `pr-spec.json`, and the `check` output before and after the local chain edit (redacted: no token or hostname appears) | `dogfood.md` |
| T12 | `make check` summary | `ci-parity.md` |

## Verification activities

- [ ] T1 — `cd cli && uv run python -m pytest -q tests/test_pr_spec.py`
- [ ] T2 — `cd cli && uv run python -m pytest -q tests/test_pr_spec_integration.py`
- [ ] T3 — `cd cli && uv run python -m pytest -q tests/test_api_contract_parity.py`
- [ ] T6 — `cd cli && uv run python -m pytest -q tests/test_graph_loops.py tests/test_manifest_schemas.py tests/test_writing_parity.py`
- [ ] T8 — `cd cli && uv run python -m pytest -q tests/test_pr_spec.py -k "abuse or forged"`
- [ ] T10 — `cd cli && uv run python -m pytest -q tests/test_graph_skips.py tests/test_graph_loops.py tests/test_graph_multirepo_integration.py`
- [ ] T11 — dogfood the verb and the stale report on PR #546
- [ ] T12 — `make check`

## Verification results

*Not yet executed.*

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed.
