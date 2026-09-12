---
type: testing-plan
phase: test-planning
workItem: "issue-352"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: nothing reads it, nothing writes it, and every moved key still works

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs;
> credentials appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `graph/extensions`: `read_declaration` parses `routing.graph.hooks`, refuses a non-mapping `routing.graph`, and an absent block is empty; `load_graph(declaration=…)` attaches, a missing module fails the load, no declaration imports nothing | `uv run --project cli python -m pytest -q cli/tests/test_graph_extensions.py` |
| T2 | Unit | yes | `critics.load_critics(path)` reads `critics[]` from a CLI config: absent → `[]`, duplicates refused, `find_critic(name, path)` names the alternatives; `load_review_policy(path)`: absent → the defaults, a partial block is defaulted, a malformed block (not a mapping, a non-integer or negative cap, a non-boolean rule) is refused; `critic policy` prints the defaulted block as JSON and as text; the command surface with `--config` | `uv run --project cli python -m pytest -q cli/tests/test_critics.py` |
| T3 | Unit | yes | `core.repo`: `scenarios` uses the caller's globs or the defaults; `instructions` takes `docs` (string or mapping) and `on_missing`; `critics` lists the CLI config's entries and **ignores a committed `reviews.critics[]`** (A1); `review_policy` reads the CLI config's `reviews` and ignores a committed one | `uv run --project cli python -m pytest -q cli/tests/test_core_repo.py cli/tests/test_cli.py` |
| T4 | Unit | yes | `instructions` command: `--doc`/`--on-missing` drive the exit code; a harness config in the checkout is never read; a malformed JSON `--doc` exits 2; notes survive through the JSON form and pipes are escaped | `uv run --project cli python -m pytest -q cli/tests/test_instructions.py` |
| T5 | Unit | yes | `graphlink`: the instance's `specDir` is honoured, a checkout's `workflow.specDir` is not consulted, an unparseable harness config changes nothing, an escaping `specDir` is refused (A3), a foreign checkout is never coupled (A4), the gate and the runtime read one directory | `uv run --project cli python -m pytest -q cli/tests/test_graphlink.py` |
| T6 | Unit | yes | `bootstrap`: `guestLoop` for contribution/review and not for the work item's loops or a PR loop; `originRepo` from the explicit argument, else the remote, never a committed `ticketing.github`; the `notify` roles and `publish-artifact` keyed on `guestLoop`; `await-inner-loops` names the unknown origin | `uv run --project cli python -m pytest -q cli/tests/test_graph_contribution.py cli/tests/test_graph_review.py cli/tests/test_graph_loops.py cli/tests/test_graph_refs.py` |
| T7 | Unit | yes | `migrations`: version `0.9.0`; `routing.graph.repoHooks` is detected, removed, reported, and the note names `critics[]` and `routing.graph.hooks` (A5) | `uv run --project cli python -m pytest -q cli/tests/test_migrations.py` |
| T8 | Integration (scenario) | yes | Gherkin-docstringed, through the real seams: a CLI-config hook gates a node and a committed-but-undeclared module is never run (A2); `the-loop critic run` spawns a CLI-config critic and a committed one is unknown; `the-loop instructions --doc` through `main`; the daemon drives two repositories under one `specDir`; the origin repository reaches refs and hosts without any harness config; the spawn pre-flight no longer adopts | `uv run --project cli python -m pytest -q cli/tests/test_graph_extensions_integration.py cli/tests/test_critics_integration.py cli/tests/test_instructions_integration.py cli/tests/test_graphlink_integration.py cli/tests/test_graph_refs_integration.py cli/tests/test_ghhost_integration.py cli/tests/test_graph_drive_integration.py` |
| T9 | Contract (schema + docs parity) | yes | the packaged CLI schema equals the authored one; the served OpenAPI surface equals the authored contract (`repoReviewPolicy` added); every CLI-config leaf (`critics[].*`, `reviews.*`, `routing.graph.hooks.*`) is documented with type and default and `repoHooks` no longer is; the runtime validator knows every keyword the schemas use; every config file validates against its schema; the templates point at a schema that exists | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_configschema.py cli/tests/test_manifest_schemas.py && uv run python scripts/validate_config.py` |
| T10 | Security / abuse case | yes | A1 (T3), A2 (T8), A3 (T5), A4 (T5), A5 (T7), A6 (`collect_docs` reads `path`/`notes` only — T4's JSON tests plus issue-132's body-never-reaches-the-report test) | the rows named |
| T11 | Static | yes | no module under `cli/the_loop/` names `harness_config`, `harness-config.default`, `repoInitialized`, `allow_repo_hooks` or `.adopt(`; no shipped prose, command, schema or docstring names a removed policy key as configuration (AC3.6); ruff, ruff format, pyright, markdownlint | `make check` plus two `grep`s recorded in the evidence |
| T12 | End-to-end | n/a — the e2e runner (`test_pdlc_e2e`) drives the real graph with a fake GitHub; it no longer writes a harness config and keeps passing, which is the end-to-end signal this change has | | |
| T13 | Performance / UI / accessibility | n/a — no hot path, no UI | | |

## Verification results

Filled at `verification`; see [`evidence/verification.md`](evidence/verification.md).

| Row | Outcome |
|-----|---------|
| T1–T8 | run, green (suite total in the evidence) |
| T9 | run, green (schema parity, docs parity, validator keywords, config validation) |
| T10 | each abuse case has a negative test, all green |
| T11 | `make check` green; grep empty |
