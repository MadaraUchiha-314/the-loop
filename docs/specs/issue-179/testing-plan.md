---
type: testing-plan
phase: test-planning
workItem: issue-179
status: approved              # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: everything can be declared away, nothing is declared away quietly

> Phase 3 of 4. Derived from the locked [`requirements.md`](requirements.md) and
> [`design.md`](design.md). Ticket:
> [issue #179](https://github.com/MadaraUchiha-314/the-loop/issues/179).
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. No credentials are involved: every test runs against temp directories and
> this repository's own checkout; nothing touches the network.

## Test matrix

| # | Type | In scope? | What it proves |
|---|------|-----------|----------------|
| M1 | Unit — the vocabulary is exactly right | yes | R1.1, R1.2: every outer-loop node is skippable **except** `phase-selection` (still `required: true`) and the terminals; asserted as a set equality so a future node cannot be added silently on either side |
| M2 | Unit — the invariant | yes | R1.2, R1.3: `phase-selection` is required and not skippable; `security-review`/`human-approval` are skippable and no longer required; `required` × `skippable` is still a compile error (the rule that enforces the invariant) |
| M3 | Unit — routing is authored | yes | R1.4: the shipped graph compiles (every skippable node declares its `on: skipped` edge), and each new edge points at the node's ordinary forward successor |
| M4 | Unit — skip sets | yes | R1.5: `spec-chain` names the seven spec-chain nodes; `review-chain` names the six review nodes; every member is skippable (compile-checked) |
| M5 | Unit — the inner loop is untouched | yes | R1.6: `pdlc-pr-loop` declares no skippable node, has no `phase-selection`, and keeps `security-review` `required: true` |
| M6 | Unit — routing end to end | yes | R1.8: with every selectable phase declared away the pointer runs `phase-selection → complete`; each intermediate node records outcome `skipped`; none of their hooks run (no phase label, no log entry, no assignment) |
| M7 | Unit — `onlyWhenSkipped` applies | yes | R3.1: the entry gates its fallback artifact when the named artifact is a planned absence (authoring node declared-skipped **and** absent) |
| M8 | Unit — `onlyWhenSkipped` does not apply | yes | R3.1–R3.3: skipped-but-present → does not apply; not skipped → does not apply; names an artifact no skippable node authors → never applies; parameter absent → today's behaviour unchanged |
| M9 | Integration — the real `verification` node, plan kept | yes | R2.1: `testing-plan.md` locked and complete → pass; its `Verification results` empty → block. No execution-log section required |
| M10 | Integration — the real `verification` node, plan declared away | yes | R2.2: no `testing-plan.md` and `test-planning` skipped → **blocks** naming `execution-log.md`; once the log carries non-empty `Verification results` → passes |
| M11 | Integration — declared but present | yes | R2.3: `test-planning` skipped and a `testing-plan.md` present → gated on the plan alone; an empty log section does not block |
| M12 | Unit — the checklist copy | yes | R1.7: with no protected phase the checklist says every phase is selectable and each omission is recorded, instead of printing an empty "always runs" block; the selectable rows still name every skippable node |
| M13 | Parity — templates, phases, manifest | yes | R2.5: `test_p5c` (every gated section exists in the artifact's template) passes, which it can only once `templates/execution-log.md` offers `Verification results`; P1–P5b unchanged |
| M14 | Regression — full suite, lint, types, docs | yes | nothing else moved: `pytest`, `ruff`, `ruff format --check`, `pyright`, `markdownlint`, `validate_config.py` |
| M15 | UI/visual, accessibility | n/a | no user-facing surface — YAML, Python and markdown only |
| M16 | Performance | n/a | one extra set-membership test per gated node; ten more edges in a ≤ 20-node graph. Nothing hot |
| M17 | Migration | n/a | additive: an already-frozen graph keeps walking the phases it froze (a skip is recorded, never inferred), and an in-flight item sees the wider checklist only at a selection it has not yet answered |
| M18 | E2E against live GitHub | n/a | no integration surface changed — the selection gate, its transports and the CLI verb are untouched |

## Verification environment

This repository's own checkout, nothing else: `uv` for the environment, `pytest` from
`cli/`, the linters from the repo root — the same commands CI runs
(`uv run --directory cli pytest -q`, `uvx ruff check`, `uv run --directory cli pyright`,
`npx markdownlint-cli2`). No second repo, no service, no secrets; integrations are faked
in-process.

## Evidence plan

Committed under [`evidence/`](evidence/):

- `tests.md` — the new tests red against the pre-change code (proving they test
  something), then green, with full-suite counts before and after.
- `walkthrough.md` — the motivating scenario end to end: a doc-fix work item declaring
  `spec-chain` + `review-chain`, `the-loop check` reporting each omission with provenance,
  and `verification` blocking until the execution log carries its results.
- `lint-and-types.md` — ruff, pyright, markdownlint and config-validation output.

## Activities checklist

- [x] M1–M13 written test-first and failing against the pre-change code where the
      behaviour is new (record the red in `evidence/tests.md`)
- [x] M1–M13 green
- [x] M14 full regression suite + lint + types green
- [x] Evidence committed and redacted (no tokens, no hostnames beyond github.com)

## Verification results

> Executed at the `verification` node on 2026-08-08. Per-activity record below; raw
> output in [`evidence/`](evidence/).

| Activity | Command | Outcome | Evidence |
|---|---|---|---|
| M1–M6, M12 vocabulary, invariant, routing, checklist | `uv run --directory cli pytest -q tests/test_graph_skips.py` | pass — 46 tests. Red first: five of them failed against the pre-change YAML and checklist (ten nodes unmarked, `security-review` still `required`, no `review-chain` set) | [`evidence/tests.md`](evidence/tests.md) |
| M7, M8 `onlyWhenSkipped` | `uv run --directory cli pytest -q tests/test_graph_hooks.py` | pass — 46 tests, four of them new. The three dormancy cases were red before the parameter existed (the entry applied unconditionally) | [`evidence/tests.md`](evidence/tests.md) |
| M9–M11 the real `verification` node | `uv run --directory cli pytest -q tests/test_graph_verification_integration.py` | pass — 10 tests, three of them new; the plan-declared-away case blocked naming `execution-log.md` before the section was written, then passed | [`evidence/tests.md`](evidence/tests.md) |
| M13 parity | `uv run --directory cli pytest -q tests/test_graph_parity.py` | pass — 8 tests; `test_p5c` red in isolation before `templates/execution-log.md` offered `Verification results`, exactly as designed | [`evidence/tests.md`](evidence/tests.md) |
| M1/M4 the operator surface | `uv run --directory cli pytest -q tests/test_core_graphs.py` | pass — 5 tests; the shipped-vocabulary case now declares seven spec-chain nodes and rejects `phase-selection` rather than `security-review` | [`evidence/tests.md`](evidence/tests.md) |
| M14 full suite | `uv run --directory cli pytest -q` | pass — 1480 passed, 1 skipped (baseline 1467 passed, 1 skipped) | [`evidence/tests.md`](evidence/tests.md) |
| M14 lint/types/config | `uvx ruff check cli` · `uvx ruff format --check cli` · `uv run --directory cli pyright` · `npx markdownlint-cli2` over the changed docs · `uv run python scripts/validate_config.py` | pass — all clean | [`evidence/lint-and-types.md`](evidence/lint-and-types.md) |
| Walkthrough (the ticket's scenario) | `the-loop graph skip` + a scripted selection-gate run against the shipped graph, then `check` and the `verification` node | pass — 13 nodes declared from two tokens with `phase-selection` refused, pointer at `implementation`, every omission reported *skipped by declaration — by whom*, `verification` blocked until the log carried its results, and a forged declaration on the gate inert and surfaced | [`evidence/walkthrough.md`](evidence/walkthrough.md) |
