---
type: testing-plan
phase: test-planning
workItem: issue-228
status: draft                # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: one `the-loop start` for every service the config enables

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md),
> before `tasks.md`. Authored at `test-planning`, **completed at `verification`** —
> the Results column and the activities checklist are filled in there.
>
> **This file is executable content**: it names commands an agent runs. All of them are
> this repository's own test/lint commands against temp directories; no credentials.

## What this work item has to prove

1. **Composition is faithful to the flags.** `start` starts exactly the enabled
   services, `stop` stops running ones regardless of flags, `status`'s exit code means
   "everything enabled is up". Unit-level with fakes, plus one real-process integration
   pass.
2. **Nothing the poll command did is lost.** The poller still runs (foreground, once,
   detached-by-spawn), still locks, still heartbeats, still hot-reloads — driven through
   its new entry points. The old tests are **re-pointed, not deleted**: each scenario
   keeps its Gherkin docstring and asserts the same behaviour via `daemon_entry` /
   `poller.daemon` / `the-loop start`.
3. **The restart API scheduls a real restart without dying mid-answer.** The route
   answers immediately with a pid; the spawned argv is fixed; the contract file matches
   the app.
4. **Fail-closed holds.** Disabled service ⇒ no auto-start; MCP disabled ⇒ `/mcp` 404;
   unloadable config ⇒ `start` refuses.

## Test-type matrix

| Type | In scope? | What / why |
|------|-----------|------------|
| Unit | yes | `core.lifecycle` plan/start/stop/status/schedule with fakes; `service_config` flag parsing; `ensure_service` refusal; `daemon_entry` arg handling |
| Integration | yes | re-pointed poller daemon tests (real subprocesses, temp state root); `the-loop start/stop/status/restart` end-to-end with service; `/api/v1/restart` over a live app; `/mcp` 404 when disabled |
| Contract | yes | OpenAPI parity test already enforces app ↔ `the-loop.v1.yaml`; restart route added to both |
| Schema/docs parity | yes | existing suites: schema copies byte-identical; docs P1–P5 over the new/removed command pages and new keys |
| e2e (PDLC) | n/a | the pdlc e2e suite exercises graph walking, untouched here |
| UI/visual | n/a | no UI change (the dashboard may adopt restart later; not in this ticket) |
| Performance | n/a | no hot path touched; start-up waits are bounded and configurable in tests |
| Security/abuse | yes | restart body rejects non-boolean shapes (pydantic); fixed-argv assertion on the spawned process; MCP-disabled 404; auto-start refusal when `service.enabled: false` |
| Accessibility | n/a | no UI |
| Migration | n/a | keys added, none removed; `migrate-config` untouched — asserted by the existing migration suite staying green |
| Manual | yes | one scripted smoke: `the-loop start` → `status` → `restart` → `stop` in a temp HOME, transcript to evidence |

## Verification environment

This repository's checkout only: `uv` workspace in `cli/`, pytest, ruff, pyright,
markdownlint. Real subprocesses bind loopback ports chosen free-at-test-time (existing
`_free_port()` pattern). No network beyond loopback; `--with-upgrade` is tested at the
plan level (dry-run) — executing a real upgrade would mutate the environment.

## Activities

> Completed at verification; raw output in
> [`evidence/verification.md`](evidence/verification.md).

| # | Activity | Command | Result |
|---|----------|---------|--------|
| T1 | ✅ New unit tests: `core.lifecycle` | `uv run pytest tests/test_core_lifecycle.py` | 10 passed |
| T2 | ✅ New unit/integration: lifecycle commands (`start`/`stop`/`status`/`restart` rendering, exit codes) | `uv run pytest tests/test_lifecycle_cmd.py` | 7 passed |
| T3 | ✅ Re-pointed poller daemon tests (foreground, `--once`, lock, status, heartbeat, ttyd wiring) | `uv run pytest tests/test_poll_daemon_integration.py tests/test_poll_command.py tests/test_poll_status.py tests/test_poll_heartbeat.py` | 37 passed (one contention-induced flake while the full suite ran concurrently, 3× re-runs green — recorded in evidence) |
| T4 | ✅ Restart API + MCP flag integration | `uv run pytest tests/test_service_lifecycle_integration.py tests/test_mcp_integration.py tests/test_api_routers_integration.py` | 19 passed |
| T5 | ✅ Contract parity (restart route in the OpenAPI file) | `uv run pytest tests/test_api_contract_parity.py tests/test_config_schema_parity.py tests/test_docs_parity.py tests/test_configschema.py` | 29 passed (run combined with T6) |
| T6 | ✅ Schema copies + docs parity + config schema validity | combined into T5's run | green: copies byte-identical, docs P1–P5 |
| T7 | ✅ Full suite | `cd cli && uv run pytest` | 2034 passed, 1 skipped (pre-existing skip); three full runs, all green |
| T8 | ✅ Lint / format / types | `make lint format-check typecheck` | ruff clean, 212 files formatted, pyright 0 errors |
| T9 | ✅ Markdown lint | part of `make lint` (markdownlint-cli2) | 658 files, 0 errors |
| T10 | ✅ Config validation (template with new keys) | `uv run python scripts/validate_config.py` (`make validate`) | all 7 configs VALID |
| T11 | ✅ Manual smoke (temp HOME): start → status → restart → stop | scripted, transcript committed | full lifecycle against a real service; exit codes as specified |
| T12 | ✅ Reference sweep: no live doc/code names `the-loop poll` outside history | `grep -rn "the-loop poll" …` excluding specs/decisions | 1 intended survivor (the new module's own docstring describing the move); 4 stragglers found and fixed |
