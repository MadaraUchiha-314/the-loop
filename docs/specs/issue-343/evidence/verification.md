---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#343"
---

# Verification: an operator can bring their own graphs and bind commands to them

> The `verification` node's record, against [testing-plan.md](../testing-plan.md)'s
> matrix. Run in this container on the repository checkout (branch
> `claude/github-issue-343-skvzmi`, on top of `4cca7fa` plus the review-round fixes
> committed with this record), with `uv` 0.12.18 installed over the image's own 0.8.17
> (`pyproject.toml` requires `>=0.12,<0.13`).

## Red first

The new tests were run against the tree **before** the implementation (the spec-only
commit `c100907`, in a separate worktree, with the new test files copied in):
`tests/test_graph_catalog.py` could not be collected (`No module named
'the_loop.graph.catalog'`), and of the other three files **21 failed, 42 passed** — every
new control, integration and scoped-attachment test failed; the passes were the
pre-existing extension tests and the unauthorized-refusal scenario, which is a guard that
must hold both before and after.

## Results

| # | Type | Command | Outcome |
|---|------|---------|---------|
| T1 | Unit | `cd cli && uv run python -m pytest -q tests/test_graph_catalog.py` | **pass** — 83 tests in the file; T1's: every R1/R3 parse rule (grammar, reserved prefix, shipped names, duplicates, unknown keys, non-list and non-string values, command classes, double binding, reserved verbs), path resolution |
| T2 | Unit | same file | **pass** — the compiler's errors on a custom graph, name mismatch, phase vocabulary (pinned equal to the shipped union), unreadable files, `x-` hook binding (declared, undeclared, no modules), the unknown-name error, `slash_command`, the repository-file warning |
| T3 | Unit | same file | **pass** — `resolve_outer_loop` (7 cases), `build_runtime` choosing/refusing/guest, R4.4 (a broken declared graph raises), `core.graphs.check` on a custom item, `_outer_loop_name` state → record loop → binding → shipped, `Runtime.start` recording the custom name |
| T4 | Unit | `cd cli && uv run python -m pytest -q tests/test_control_custom_commands.py` | **pass** — 16: bindings, new-word parse, overrides, boundaries, ambiguity, case, keyword clash, the record's `loop` round trip and an older record |
| T5 | Integration | `cd cli && uv run python -m pytest -q tests/test_custom_graph_integration.py` | **pass** — 3 Gherkin scenarios over a real dispatcher and a real `git` checkout: `the-loop triage` arms and the work item's state walks `acme-triage-loop` from `triage`; an overridden `do` walks `acme-quick-loop`; an unauthorized `the-loop triage` records, spawns and enters nothing |
| T6 | Unit | `cd cli && uv run python -m pytest -q tests/test_graph_extensions.py` | **pass** — 45 in the file; the new 4: scoped attachment skipped/applied, unknown and empty `loops` refused, a declared loop as a scope, digest changes |
| T7 | Unit | `tests/test_graph_catalog.py -k loops` | **pass** — text and JSON rows, a broken graph exits 1, no module imported, an unreadable declaration and an unparseable config exit 1, attachment and `x-` checks, configured keywords, and a **fresh-process** run of the real CLI |
| T8 | Security | the three files above | **pass** — each abuse case's named negative test (see [security-review.md](security-review.md)) |
| T9 | Contract / schema | `cd cli && uv run python -m pytest -q tests/test_config_schema_parity.py tests/test_configschema.py tests/test_docs_parity.py` | **pass** — 53: both schema copies identical, samples validate, every new schema leaf has a docs heading |
| T10 | Regression | `cd cli && uv run python -m pytest -q` | **pass** — 4634 passed, 1 skipped, 180 s (baseline before the change: 4528 passed, 1 skipped) |
| T11 | Manual exploratory | — | **not run** — needs a GitHub repository and a running daemon; T5 drives the same dispatcher with the same comment against a real checkout |
| T12 | Documentation parity | `npx markdownlint-cli2@0.18.1` over every changed page | **pass** — 0 errors over 17 files |
| T13 | Performance | — | **n/a as planned** — one cached compile per declared graph per process |
| T14 | UI | — | **n/a as planned** — no product UI |

The rest of `make check`: `uv run ruff check cli hooks` — all checks passed;
`uv run ruff format --check cli hooks` — 358 files already formatted;
`uv run pyright cli` — 0 errors, 0 warnings.

## What the run proves, in one line each

- A graph the operator declares is compiled by the shipped rules and walked by the real
  runtime when an authorized user types the word bound to it (T2, T5).
- An overridden shipped command walks the operator's graph, however the item was armed
  (T3, T5).
- Nothing but the operator's current declaration can make a recorded name select a custom
  graph (T3, T8).
- An operator who declares nothing sees no change (T10).

## Re-run after the owner's reshape (PR #425 review)

The declaration moved to top-level `graphs` plus `routing.control.commands`. The same
matrix was re-run on the reshaped tree:

| # | Command | Outcome |
|---|---------|---------|
| T1–T3, T7 | `cd cli && uv run python -m pytest -q tests/test_graph_catalog.py` | **pass**: 105 tests. New: binding validation (undeclared graph, `keyword` on a built-in, malformed entries), the loader's `routing._graphs` fan-in, a binding to the default loop, a new word's own keyword in `graph loops`, and a binding to an undeclared graph reported by `graph loops` |
| T4 | `cd cli && uv run python -m pytest -q tests/test_control_custom_commands.py` | **pass**: 23 tests, including a new word's `keyword`, a clash with a built-in keyword, re-pointing at a shipped loop, and a new word onto a shipped loop |
| T5 | `cd cli && uv run python -m pytest -q tests/test_custom_graph_integration.py` | **pass**: the 3 scenarios. The dispatcher is now built from `load_cli_config`'s output, so the fan-in is on the path |
| T9 | `cd cli && uv run python -m pytest -q tests/test_config_schema_parity.py tests/test_configschema.py tests/test_docs_parity.py tests/test_onboarding_schema.py` | **pass**: the copies are identical, the new shape validates and `routing.graph.graphs` does not, every leaf has a heading, and `graphs` is in the `execution` onboarding group |
| T10 | `cd cli && uv run python -m pytest -q` | **pass**: 4659 passed, 1 skipped, 185 s |
| T12 | `npx markdownlint-cli2@0.18.1` over every changed page | **pass**: 0 errors |

Also clean: `uv run ruff check cli hooks`, `uv run ruff format --check cli hooks` (358
files) and `uv run pyright cli` (0 errors).
