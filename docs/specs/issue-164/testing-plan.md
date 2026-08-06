---
type: testing-plan
phase: test-planning
workItem: issue-164
status: approved              # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: the module structure a work item will produce

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md).
> Authored at `test-planning`, completed at `verification`.
>
> **This file is executable content.** Review the commands like code. No credentials are
> involved — every command reads this repository and nothing else.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `test_graph_model.py` — the `design` node's gate demands exactly `Architecture`, `Module structure`, `Security design`, `Testing strategy`, and is locked | `make test` |
| T2 | Unit (parity) | yes | `test_graph_parity.py` P3 — the bundled `design.md` template offers every section the graph gates, read through the gate's own heading parser | `make test` |
| T3 | Unit (hook) | yes | `test_graph_hooks.py` — a design with the heading missing blocks; a design with the heading present but empty blocks with a distinct finding | `make test` |
| T4 | Integration (scenario) | n/a — the change adds no runtime path: no dispatch, no routing, no session. The gate it extends is already covered by the graph integration suite, and this change adds a string to its section list, not a code path. | | |
| T5 | Contract (OpenAPI / GraphQL SDL) | n/a — no API surface. `docs/api-specs/openapi` is untouched. | | |
| T6 | End-to-end | n/a — no user-invocable flow is added; `/the-loop:create-design` gains a sentence, not a step. | | |
| T7 | UI / visual | n/a — no user-facing surface (`design.uiArtifacts` produces nothing for docs/process work). | | |
| T8 | Security / abuse case | yes | the abuse cases in `design.md` §Security design: an empty section cannot tick the box, a docs-only work item can still clear the gate, and no code consumes a listed path | `make test` + inspection |
| T9 | Snapshot | n/a — no rendered output to freeze. | | |
| T10 | Performance / load | n/a — one extra string comparison per gate run. | | |
| T11 | Accessibility | n/a — no UI. | | |
| T12 | Migration / upgrade | yes | a repository scaffolded before this change: existing `docs/specs/*/design.md` files are not retro-fitted, and no build goes red over them | `make test` + `make lint` |
| T13 | Manual exploratory | yes | read the rendered template section as an author, and this spec's own `## Module structure` as a reviewer: can the modules be named without opening `tasks.md` or the diff (R4.1)? | manual |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R2.1 | the `design` gate's section set includes `Module structure` and the artifact stays locked |
| T2 | R1.1, R2.3 | the bundled template offers the gated section — template↔graph parity in both directions |
| T3 | R2.2 | a missing section blocks the node with a finding naming it |
| T3 | R2.2, R1.6 | a present-but-empty section blocks with the empty-section finding, so "TBD" is the only way through and it is visible |
| T8 | abuse case 2 | the empty-section case above, read as the box-ticking defence |
| T8 | abuse case 3, R1.6 | a docs-only design whose section is one sentence clears the gate |
| T8 | abuse case 1 | no statement added to `cli/` reads, resolves or fetches a path listed in the section (inspection of the diff) |
| T12 | R2.1 | pre-existing specs are untouched; gates run forward |
| T13 | R1.2, R1.3, R4.1, R4.2 | the tree, the table and the scoping rule are usable as written |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none.
- **Fixtures & data:** none beyond the `tmp_path` specs the graph hook tests already build.
- **Credentials:** none. No command here touches a secret.
- **Bring-up:** `make install-dev` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T3, T8, T12 | pytest output for the graph suites plus the full suite | `unit.md` |
| all | `make lint`, `make format-check`, `make typecheck`, `make validate` output | `checks.md` |
| T8, T12 | the abuse-case inspection and the no-retro-fit check | `abuse-cases.md` |
| T13 | the manual read-through finding | Verification results, below |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_graph_model.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_graph_parity.py`
- [x] T3 — `uv run --project cli python -m pytest -q cli/tests/test_graph_hooks.py`
- [x] T1/T2/T3/T12 — `make test` (full suite: no regression from the graph and template edits)
- [x] T8 — the docs-only and empty-section cases, plus a read of the diff for any new
      statement in `cli/` that touches a path from the section
- [x] all — `make lint`, `make format-check`, `make typecheck`, `make validate`
- [x] T13 — read `skills/the-loop/templates/design.md` §Module structure as an author and
      this spec's own section as a reviewer; record whether R4.1 holds

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `pytest -q cli/tests/test_graph_model.py` | 40 passed — the design gate's section set is exactly the four, and the artifact stays locked | [`evidence/unit.md`](evidence/unit.md) |
| T2 | `pytest -q cli/tests/test_graph_parity.py` | 5 passed — the bundled template offers every gated section. No edit to this test was needed: it walks the graph | [`evidence/unit.md`](evidence/unit.md) |
| T3 | `pytest -q cli/tests/test_graph_hooks.py` | 32 passed — missing blocks, empty blocks, one-sentence no-code answer passes, all against the shipped gate's own params | [`evidence/unit.md`](evidence/unit.md) |
| T1/T2/T3/T12 | `make test` | 1345 passed, 1 skipped | [`evidence/unit.md`](evidence/unit.md) |
| — | the red state before task 2 | 3 failed, 69 passed — the assertions named `Module structure` as the missing item | [`evidence/unit.md`](evidence/unit.md) |
| T8 | the three abuse cases, plus a read of every change under `cli/` | no new statement consumes a listed path (the only non-test change is one YAML string); the empty-section and docs-only cases are executed tests | [`evidence/abuse-cases.md`](evidence/abuse-cases.md) |
| T12 | `git status --porcelain -- docs/specs/` | the only change under `docs/specs/` is this work item's own directory — no design was re-authored to satisfy the new heading | [`evidence/abuse-cases.md`](evidence/abuse-cases.md) |
| all | `make lint`, `make format-check`, `make typecheck`, `make validate` | ruff clean · markdownlint 0 errors over 432 files · pyright 0 errors · all six configs valid | [`evidence/checks.md`](evidence/checks.md) |
| T13 | read the template section as an author and this spec's own section as a reviewer | R4.1 holds; one finding, below | this table |

**T13 finding — the tree and the table are not redundant, and the template now says why.**
Reading the section as an author, the obvious cut is one of the two: the tree and the table
carry the same paths. Keeping both is deliberate. The tree shows **nesting** — that
`cli/tests/` and `cli/the_loop/graph/` are siblings is a fact a flat table cannot state — and
the table carries the **requirement column**, which is what makes the section checkable: a
path with no requirement behind it is either scope creep or a requirement nobody wrote down.
Cutting either one loses information, which is the density test's own answer.

Read as a reviewer, [`design.md`](design.md) §Module structure names all eleven touched
paths, their status and the requirement each serves, without `tasks.md` or the diff being
open — R4.1 as specified.

**Not executed:** none. Every in-scope activity ran.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
