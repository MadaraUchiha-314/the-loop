---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#451"
status: in-review            # draft | in-review | approved — locked with design.md
approvedBy: []
overrides: {}
riskTier: 4
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: a default model per harness in `cli-config.yaml`

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md). Results
> are recorded in [`evidence/verification.md`](evidence/verification.md).

## What "proved" means here

- A session that chose no model launches with `--model <defaultModel>` of its own
  harness, and a session that chose one launches on its choice.
- No value outside the model-name grammar reaches an argv.
- An install without the key launches byte-identically to today.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (vocabulary) | yes | `default_model` returns the entry's value; `""` for no entry, another harness's entry, a non-string, a flag-shaped or shell-shaped value; not tied to `models[]`; the no-model-flag finding (R1.2, R1.3, R2.5, abuse 1, 3) | `tests/test_modelchoice.py` |
| T2 | Integration (dispatcher) | yes | real dispatcher over the fake tmux: no frozen model → default appended after `args`; frozen model wins; forged/undeclared frozen model → default; refused default dropped; record names the default; default not applied on another harness; no key → shared adapter untouched (R2.1–R2.4, R2.6, R5.1, abuse 2, 3) | `tests/test_dispatcher_choice.py` |
| T3 | Unit (gate) | yes | checklist tail and confirmation name the default; unchanged text without one (R3.1, R3.2, R5.1) | `tests/test_selection_choices.py` |
| T4 | Unit (probe matrix) | yes | `_combinations` includes each harness's default once (R4.1) | `tests/test_models_cmd.py` |
| T5 | Static (schema) | yes | both schema copies accept `defaultModel`, reject a flag-shaped value; the repo's configs validate (R1.1) | `make validate`, `tests/test_modelchoice.py` |
| T6 | Negative control | yes | T1–T4 fail on the unchanged source | the modules above |
| T7 | Regression (full suite) | yes | green from `cli/`, CI's command | `make test` |
| T8 | Static | yes | `ruff format --check`, `ruff check`, `pyright`, markdownlint | `make lint format-check typecheck` |
| T9 | Manual (real harness) | n/a: the argv is asserted end to end through the real dispatcher in T2; launching a real `claude` needs credentials this environment does not hold | | |
| T10 | UI / visual | n/a: no UI surface changes | | |
| T11 | Contract (OpenAPI) | n/a: no route or API schema changes | | |
| T12 | Performance | n/a: one dict lookup per launch over a config already in memory | | |

## Scenarios & requirement trace

| Requirement | Rows |
|---|---|
| R1 | T1, T5 |
| R2 | T1, T2 |
| R3 | T3 |
| R4 | T4 |
| R5 | T2, T3 |
| Abuse 1–3 | T1, T2 |

## Verification environment

This repository's own checkout: `uv sync`, then the Makefile targets from the root. No
external services, fixtures or credentials.

## Activities

- [x] T1–T5 written red first, then green
- [x] T6 negative control run
- [x] T7 full suite green
- [x] T8 static checks green
