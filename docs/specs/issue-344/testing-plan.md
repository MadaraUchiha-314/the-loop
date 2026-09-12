---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#344"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: lifecycle hooks — every recorded event is an attach point

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md),
> before `tasks.md`. Authored at `test-planning`; the results section is filled at
> `verification`.
>
> **This file is executable content.** Commands below are what the agent runs;
> credentials appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit — declaration | yes | `read_declaration`: an absent/empty block is empty; `on` as a string or a list; a non-mapping block, a non-list `lifecycle`, a missing `hook`/`on`, a non-mapping `with` are refused naming the entry; a name that is neither `x-` nor shipped is refused naming the shipped names; a pattern is expanded against the catalog at parse and one matching nothing fails; `hooks.*` is never an attach point; a shipped hook's parameters are validated at parse | `uv run --project cli python -m pytest -q cli/tests/test_lifecycle_hooks.py -k declaration` |
| T2 | Unit — loading | yes | `LifecycleHooks.load`: a `path` resolves against the config directory; absolute, `..` and symlink-out are refused (A2); a missing/raising/empty module, a non-`x-` registration and a duplicate across modules fail naming the module; an attachment to a hook no module registered fails; a shipped hook resolves without any module; `hooks.loaded` is emitted with the counts | `… -k load` |
| T3 | Unit — dispatch | yes | order across attachments, `params` and `fields` reach the hook, the record is copied; `hooks.*` never dispatched (A4); a record emitted on the worker thread is not re-dispatched (A4); a raise and a `block` are one `hooks.failed` each and the next hook runs (A3); `None`/`ok` succeed and `messages` become no event; an `outcome` is ignored (A5); overflow drops for hooks only and emits `hooks.dropped` once per episode (A9); `drain` returns true when idle and false on timeout with a hung hook (A3) | `… -k dispatch` |
| T4 | Unit — `forward-event` | yes | against a local `http.server`: body is the record, `Content-Type`, `headers` verbatim, bearer from the named variable read at call time; unset variable → nothing sent, `blocked` naming the variable and not a value (A6); non-2xx and connection refused → `blocked`, no retry; `validate_forward` refuses missing url, `file:`/`ftp:` schemes (A7), bad `tokenEnv`/`headers`/`timeoutSeconds` | `… -k forward` |
| T5 | Unit — event-log seam | yes | `emit` hands the record to sinks even with `eventLog.enabled: false`; a raising sink never propagates; `configure_from_file` installs the runtime from the `hooks` block and lets a `HooksConfigError` propagate (A8); `reset()` clears sinks and runtime | `uv run --project cli python -m pytest -q cli/tests/test_eventlog.py cli/tests/test_lifecycle_hooks.py -k seam` |
| T6 | Unit — command | yes | `the-loop hooks` text and json: attach-point count, shipped names, modules with the resolution root, each attachment's matched events; a module that raises on import is **not** imported (the report succeeds); a malformed block exits 2 with the message on stderr; the command is registered | `uv run --project cli python -m pytest -q cli/tests/test_hooks_cmd.py` |
| T7 | Integration (scenario) | yes | Gherkin-docstringed, through the real seams: a CLI config file + a module file under its directory → `configure_from_file("cli")` → `eventlog.emit("session.spawned", …)` → the hook received the record (work start), and `work_item.ended` (work finish); a hook module committed in a checkout that the config never names is never imported (A1); `forward-event` end-to-end to a local server with the token from the environment; a broken declaration fails `configure_from_file` (A8) | `uv run --project cli python -m pytest -q cli/tests/test_lifecycle_hooks_integration.py` |
| T8 | Contract (schema + docs parity) | yes | the packaged CLI schema equals the authored one; every `hooks.*` leaf is documented with type and default (P3/P4/P5); the new command has a page (P1/P2); every emitted event type is catalogued (`hooks.loaded`, `hooks.failed`, `hooks.dropped`); both CLI configs and the template validate | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py cli/tests/test_manifest_schemas.py && uv run python scripts/validate_config.py` |
| T9 | Security / abuse case | yes | A1 (T7), A2 (T2), A3 (T3), A4 (T3), A5 (T3), A6 (T4, T7), A7 (T4), A8 (T5, T7), A9 (T3) — each a named negative test | the rows named |
| T10 | Regression — graph hooks | yes | the graph-hook suites are unchanged and green after the loader refactor | `uv run --project cli python -m pytest -q cli/tests/test_graph_extensions.py cli/tests/test_graph_extensions_integration.py` |
| T11 | Static | yes | ruff, ruff format, pyright, markdownlint, config validation — the whole repository check | `make check` |
| T12 | End-to-end | n/a — the e2e runner (`test_pdlc_e2e`) drives the graph with a fake GitHub and configures no `hooks` block; the daemon→hook path is T7 through the same `configure_from_file` every daemon calls | | |
| T13 | UI / visual / accessibility | n/a — no user-facing surface | | |
| T14 | Performance / load | n/a as a benchmark — the bound (1024) and the non-blocking emit are asserted functionally in T3; the undeclared cost is one `None` check | | |
| T15 | Migration | n/a — an additive key; a pre-existing config without it is the empty declaration (T1) | | |
| T16 | Manual | n/a — every behaviour is a unit or integration test; the `the-loop hooks` output is captured in the evidence | | |

## Scenarios & requirement trace

| Scenario (Gherkin docstring) | Requirement | Row |
|---|---|---|
| A hook attached to `session.spawned` receives the record when the daemon's entry point emits it | R1, R4 | T7 |
| A hook attached to `work_item.*` receives `work_item.ended` | R1 | T7 |
| A checkout module the config never names is never imported | R2 (A1) | T7 |
| `forward-event` POSTs the record with the bearer token from the environment | R5 (A6) | T4, T7 |
| A broken declaration fails the entry point rather than running without hooks | R6 (A8) | T5, T7 |

## Verification environment

- **Repos:** this checkout only.
- **Services:** none external; T4/T7 start a local `http.server` on an ephemeral port.
- **Fixtures:** `tmp_path` config files and module files; `monkeypatch.setenv` for
  `THE_LOOP_CLI_CONFIG` and the token variable (a placeholder value, never a real one).
- **Credentials:** none.
- **Commands:** as in the matrix; run from the project root.

## Evidence plan

- `evidence/verification.md` — per-row command and raw output; the red-first run (the new
  suites do not collect on the base commit); the `the-loop hooks` output for this
  repository's config; the `make check` summary.
- `evidence/security-review.md` — the abuse-case table with the test that closes each,
  the checklist, residual risks, and the tier-4 sign-off status.

## Verification activities

- [x] T1–T6 unit suites green
- [x] T7 integration suite green
- [x] T8 parity and config validation green
- [x] T9 every abuse case mapped to a passing negative test
- [x] T10 graph-hook suites unchanged and green
- [x] T11 `make check` green
- [x] evidence committed and redacted

## Verification results

Filled at `verification`; see [`evidence/verification.md`](evidence/verification.md).

| Row | Outcome |
|-----|---------|
| T1–T7 | run, green — 74 tests (66 unit, 4 command, 4 integration); red first (the suites do not collect on the base) |
| T8 | run, green — schema copies identical, P1–P5 parity, event catalog, six config files valid |
| T9 | A1–A9 each closed by a named negative test (table in `evidence/security-review.md`) |
| T10 | run, green — 47 graph-hook tests unchanged |
| T11 | `make check` green: ruff, markdownlint (1097 files), format, pyright, validate, **3575 passed, 1 skipped** |

## Review comments

None yet.
