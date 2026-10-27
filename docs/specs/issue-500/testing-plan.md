---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#500"
status: draft                # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: record-feedback appends duplicate sibling headings when a gate is approved twice on one day

Everything is proved in this repository with the existing pytest suite, plus one run of
the pinned markdownlint over a twice-recorded artifact. The hook is pure file I/O on a
temporary directory; no service, credential or network is involved.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | n/a — `_unique_heading` is exercised through the hook in T2; a separate unit test would assert the same strings twice | | |
| T2 | Integration (scenario) | yes | two and three same-day recordings into one artifact yield distinct `###` headings; a first recording is unchanged; earlier headings are untouched (R1, R2, R3.1) | `uv run pytest cli/tests/test_graph_integration.py` |
| T3 | Contract | n/a — no API, schema or CLI shape changes | | |
| T4 | End-to-end | n/a — the gate calls the same hook function T2 calls; no live GitHub needed | | |
| T5 | UI / visual | n/a — no UI | | |
| T6 | Snapshot | n/a — no snapshot surfaces | | |
| T7 | Performance | n/a — one linear scan of an artifact the hook already reads | | |
| T8 | Security / abuse case | n/a — the heading takes no untrusted input (design §Security design); the existing authorization tests for `classify-feedback` are unchanged and run in T12 | | |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | n/a — artifacts already on disk are read, never rewritten (R2.2) | | |
| T11 | Real linter over a recorded artifact | yes | the shape T2 asserts is the shape MD024 accepts (R3.2) | `npx --yes markdownlint-cli2@0.18.1 <artifact>` |
| T12 | Full suite + lint/type | yes | nothing else depended on the old heading | `make check` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T2 | R1.1, R1.3, R3.1 | `Scenario: a gate approved twice on one day records distinct headings` |
| T2 | R1.2, R2.1, R2.2 | same scenario: the first heading stays `<date> — approved`, byte-identical after the later recordings |
| T11 | R3.2 | the artifact T2's scenario produces, written out and linted |
| T12 | R2.1 | the issue-247 tests (attribution, empty body) still pass |

## Verification environment

The repository checkout with `make install-dev` done; Node.js for `npx` (T11 only). No
credentials.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T2 | the new test failing before the fix, passing after | `integration.md` |
| T11 | the recorded artifact and the linter's summary | `markdownlint.md` |
| T12 | `make check` summary | `lint-and-typecheck.md` |

## Verification activities

- [ ] T2 — the new scenario fails on the pre-fix hook and passes after
- [ ] T11 — markdownlint reports 0 issues on a twice-recorded artifact
- [ ] T12 — `make check` passes

## Verification results

_Not yet executed._

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |
