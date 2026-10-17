---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#494"
status: draft                # design-approval was declared skipped for this item; reviewed on PR #495
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: gate the brainstorm on its author's approval

> Derived from [`bugfix.md`](bugfix.md) and [`design.md`](design.md). Results are filed
> under *Verification results* below, with the raw output in
> [`evidence/verification.md`](evidence/verification.md).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (graph shape) | yes | `brainstorm-approval` is a human, skippable node in `spec-chain`; the edge table in `design.md` holds exactly; every skippable node still routes `skipped` where completing it would | `cli/tests/test_graph_skips.py`, `cli/tests/test_graph_model.py` |
| T2 | Unit (hook) | yes | `validate-artifacts` with `absentOutcome` on an optional node with no artifact returns a skip carrying that outcome; without the parameter, or with the artifact present, its result is unchanged | `cli/tests/test_graph_runtime.py` (or the hook's own test module) |
| T3 | Integration (runtime walk) | yes | over a temporary spec directory with real chains: (a) `brainstorm.md` present → `brainstorm-approval`, parked; (b) an indecisive authorized comment keeps it parked; (c) an unauthorized "approved" keeps it parked; (d) an authorized "approved" records the feedback, locks `brainstorm.md` and reaches `requirements-definition`; (e) "changes requested" returns to `brainstorming`; (f) no `brainstorm.md` → `requirements-definition` directly | `cli/tests/test_graph_integration.py` |
| T4 | Integration (declared skips) | yes | `brainstorming` declared skipped never enters the gate; `brainstorm-approval` declared skipped alone routes `brainstorming` → `requirements-definition` on `pass` | `cli/tests/test_graph_integration.py` |
| T5 | E2E scenarios | yes | the shipped scenarios that pin the walk (`happy-path` and its siblings) still pass with the new node in the frozen graph; their pinned node lists gain `brainstorm-approval~` | `cli/tests/test_pdlc_e2e_integration.py` |
| T6 | Snapshot (checklist) | yes | the `phase-selection` checklist renders a ticked `brainstorm-approval` row after `brainstorming`; the Jira wiki/ADF/read fixtures match | `cli/tests/test_jira_integration.py`, selection tests |
| T7 | Regression | yes | ruff, ruff format, pyright, the full CLI suite, markdownlint, `make validate` (`make check`) | repository checks |
| T8 | Security / abuse case | yes | the unauthorized-approval abuse case is T3(c); repository-hook routing is already pinned by the extensions tests, re-run in T7 | T3, `cli/tests/test_graph_extensions.py` |
| T9 | Documentation | yes (review) | every file in the design's documentation table describes the gate, and no doc still says a brainstorm has no gate | `grep` over `skills/`, `commands/`, `docs/capabilities/`, recorded in `evidence/documentation.md` |
| T10 | UI / accessibility / performance / migration / contract | n/a | no UI or API surface changes; one dict lookup per chain; no schema or state-file change, so no migration | |

## Requirement trace

| Requirement | Tests |
|-------------|-------|
| R1.1 | T1, T3(a) |
| R1.2 | T3(b) |
| R1.3 | T3(d) |
| R1.4 | T3(e) |
| R1.5 | T1, T3(c), T8 |
| R1.6 | T3 (fails before the graph change, passes after) |
| R2.1 | T2, T3(f) |
| R2.2, R2.3 | T1, T4, T6 |
| R2.4 | T2 |
| R3.1, R3.2 | T9 |

## Verification environment

This checkout. Python through `uv` (`make install-dev`), and the tests through
`make test`, which is the pre-commit hook's own command. No service, credential or
network access is needed: every GitHub interaction in these tests goes through the
suite's existing fakes.

## Evidence plan

- `evidence/verification.md` — commands, pass/fail counts and the before/after of the
  regression tests (red on `main`, green on the branch).
- `evidence/documentation.md` — the T9 grep and the files changed.
- The usual review records (`self-review.md`, `critic-review.md`, `security-review.md`,
  `final-validation.md`, `pull-requests.md`).

## Activities

- [x] Run T1–T6 and confirm the new tests fail on `main`'s graph.
- [x] Run `make check` (T7).
- [x] Run the T9 documentation grep.

## Verification results

| Activity | Outcome | Evidence |
|----------|---------|----------|
| T1–T6 | pass on the branch; the 9 regression tests fail with `origin/main`'s graph and hooks | [`evidence/verification.md`](evidence/verification.md) |
| T7 | lint, format, pyright, markdownlint and `validate` clean. Full suite: 6125 passed, 21 failed, and the same 21 fail on `main` in this environment (they read the host's live poller) | [`evidence/verification.md`](evidence/verification.md) |
| T8 | the unauthorized-approval case is pinned in `test_a_written_brainstorm_waits_at_its_gate_across_comments`; the extensions tests pass | [`evidence/verification.md`](evidence/verification.md) |
| T9 | only new wording and the issue-281 History row match | [`evidence/documentation.md`](evidence/documentation.md) |

T5 needed no scenario edits, and T3 found the `check --recompute` defect that
`whenPresent` fixes; both are explained in the evidence.
