---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#343"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
riskTier: 4
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: an operator can bring their own graphs and bind commands to them

> Derived from [requirements.md](requirements.md) and [design.md](design.md), before
> `tasks.md`. Authored at `test-planning`, completed at `verification`.

## What is testable here, and what is not

Everything this change adds is a parser over a mapping, a compiler over a YAML file, a
name resolver, a comment parser and a dispatcher branch — and the suite already drives each
shape: `test_graph_extensions.py` compiles graphs against a `tmp_path` repository,
`test_control.py` parses comment bodies, and `test_control_integration.py` runs the real
dispatcher with the session layer faked at its injection point. No network, no real
provider, no tmux.

One row cannot run here: arming a real ticket on a real daemon (T11) needs a GitHub
repository and a running instance. T5 drives the same dispatcher with the same comment.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `read_catalog` / `read_bindings`: every R1 and R3.1–R3.4 rule (grammar, reserved prefix, shipped names, duplicates, unknown keys, command classes, a binding to an undeclared graph, `keyword` only on a new word), the loader's `routing._graphs` fan-in, path resolution against a base, an absent block | `cd cli && uv run python -m pytest tests/test_graph_catalog.py` |
| T2 | Unit | yes | `compile_custom` / `load_graph`: same compiler errors, `name` mismatch, unknown phase, missing/invalid file, `x-` hook resolution (declared, undeclared, no modules), the unknown-name error, the cache, `slash_command`, the `command:` grammar on every shipped loop | `cd cli && uv run python -m pytest tests/test_graph_catalog.py` |
| T3 | Unit | yes | `resolve_outer_loop(name, declared)`, `build_runtime` choosing / refusing / guest, `_outer_loop_name` state-first then record `loop` then command, `core/graphs._recorded_loop` | `cd cli && uv run python -m pytest tests/test_graph_catalog.py` |
| T4 | Unit | yes | `ControlConfig` bindings and keywords, `parse_command` for a new word, an override, an undeclared word, ambiguity; `ControlRecord` `loop` round trip and an older record without it | `cd cli && uv run python -m pytest tests/test_control_custom_commands.py` |
| T5 | Integration (scenario) | yes | The dispatcher end to end: an authorized `the-loop triage` arms and records `loop`, the spawn enters the custom graph and `work-item-state.json` records its name; an overridden `do` does the same; an unauthorized new command is refused | `cd cli && uv run python -m pytest tests/test_custom_graph_integration.py` |
| T6 | Unit | yes | `attach[].loops`: scoped attachment skipped on other loops, applied on its own, unknown loop refused, digest changes, unscoped behaviour unchanged | `cd cli && uv run python -m pytest tests/test_graph_extensions.py` |
| T7 | Unit | yes | `the-loop graph loops`: text and JSON rows for shipped and declared loops, a broken graph reported with exit 1, no module imported | `cd cli && uv run python -m pytest tests/test_graph_catalog.py -k loops` |
| T8 | Security / abuse case | yes | The six abuse cases of `requirements.md`, each a named negative test (design § Security design table) | `cd cli && uv run python -m pytest tests/test_graph_catalog.py tests/test_control_custom_commands.py tests/test_custom_graph_integration.py` |
| T9 | Contract / schema | yes | Both copies of `cli-config.schema.json` stay identical; the documented shape (top-level `graphs`, `routing.control.commands`) validates and the retired `routing.graph.graphs` does not; the shipped sample configs validate | `cd cli && uv run python -m pytest tests/test_config_schema_parity.py tests/test_configschema.py tests/test_docs_parity.py tests/test_graph_catalog.py -k schema` |
| T10 | Regression | yes | The whole Python suite — the control parser, the dispatcher, the graph coupling and every shipped loop are touched | `make test` |
| T11 | Manual exploratory | yes | A real daemon: declare a graph and a new command, type it on a ticket, watch the session walk the custom graph | an operator's instance; not available in this environment |
| T12 | Documentation parity | yes | Capability docs, the config reference and the skill describe the feature; markdown lint green | `make lint` |
| T13 | Performance | n/a — one extra YAML compile per declared graph per process, cached like the shipped loops; no hot path gains work | | |
| T14 | UI / accessibility / visual | n/a — the-loop has no product UI; the new surface is a config key and a CLI verb | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1–R1.5 | `a malformed or colliding declaration fails to load, naming the entry` |
| T1 | R3.1–R3.3 | `a command binds to one graph, and only an arming command can be overridden` |
| T2 | R2.1–R2.6 | `a custom graph is held to the shipped compiler, the phase vocabulary and the hook registry` |
| T3 | R4.1–R4.4, R5 | `only a declared name selects a custom graph, on every path; guest follows the declaration` |
| T4 | R3.4–R3.6, R3.8 | `a declared word parses as start with a loop; an undeclared one is no command` |
| T5 | R3.5, R3.6, R4.1 | `Scenario: a new command arms a work item onto the operator's graph` |
| T5 | R3.6 | `Scenario: an overridden arming command selects the operator's graph` |
| T5 | abuse 3 | `Scenario: an unauthorized user's new command is refused` |
| T6 | R6.1, R6.2 | `an attachment scoped to loops leaves every other loop alone` |
| T7 | R7.1–R7.3 | `graph loops lists and checks every loop without importing a module` |
| T8 | abuse 1–6 | design § Security design table |
| T2 | R8 | `a repository's graph file is ignored, and the warning names the top-level graphs` |

## Verification environment

This container, against the repository checkout: `uv sync` (with `uv` ≥ 0.12), then
`cd cli && uv run python -m pytest -q` — the command `make test` and the `pytest`
pre-commit hook run. Linting is `uv run ruff check cli hooks`, `uv run ruff format --check
cli hooks`, `uv run pyright cli` and `markdownlint-cli2`, matching `make check`. No network:
sessions and GitHub writes are faked at their injection points.

## Evidence to capture

Under `docs/specs/issue-343/evidence/`:

- `verification.md` — each row of this matrix with its command, outcome and counts.
- `self-review.md` — the review cycles and every finding's disposition.
- `security-review.md` — each abuse case with the mechanism and the test establishing it;
  the tier-4 named sign-off requested.
- `documentation.md` — the capability, config and skill docs updated in this PR.

## Verification results

Recorded at the `verification` node in
[evidence/verification.md](evidence/verification.md): T1–T10 and T12 pass (4634 passed,
1 skipped in the full suite); T13 and T14 are `n/a` as planned; T11 did not run for want of
a real repository and daemon — T5 walks the same dispatcher with the same comment against a
real checkout.

## Activities checklist

- [x] T1–T4, T6, T7 unit tests written red, then green
- [x] T5 integration scenarios written with Gherkin docstrings, red then green
- [x] T8 abuse cases asserted in the suite, not only in prose
- [x] T9 schema parity and sample validation green
- [x] T10 full `make test` green
- [x] T12 docs updated; lint green
- [x] Evidence committed
