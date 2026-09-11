---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#339"
status: draft                # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: one state root per configuration, and health surfaces that report on it

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `resolve_state_root` / `apply_state_root` over the resolution table (absent, relative, nested `.the-loop`, absolute, `~`, non-string); `rival_roots`; the health body's status computation; the spawn environment each of the three sites builds | `uv run pytest cli/tests/test_cli_config.py cli/tests/test_state.py cli/tests/test_core_daemons.py cli/tests/test_client.py` |
| T2 | Integration (scenario) | yes | the two behaviours only a scenario states: **one config file read from two working directories resolves to one root**, and **`/api/v1/health` is `degraded` with an enabled poller absent**; plus `ingress.hosted_failed` reaching the event log, and `status` naming its config, root and a rival | `uv run pytest cli/tests/test_state_root_integration.py cli/tests/test_api_health_integration.py` |
| T3 | Contract (OpenAPI) | yes | the health response's new fields are in `docs/api-specs/openapi/` and the served surface matches it | `uv run pytest cli/tests/test_api_contract_parity.py` |
| T4 | End-to-end | n/a — an E2E would need a real GitHub source and a 17-hour clock; T2 reproduces the divergence deterministically with two `cwd`s and a `TestClient`. | | |
| T5 | UI / visual | n/a — no UI surface changes. The dashboard reads `/api/v1/health` but renders no new field in this change. | | |
| T6 | Snapshot | n/a — the one rendered surface (`status`'s text) is asserted line-by-line in T1/T2, which says what changed; a snapshot would only say *that* it changed. | | |
| T7 | Performance / load | n/a — the added work is one `Path.resolve()` per config load and, per `/health` call, three `flock` probes already performed by `the-loop status`. | | |
| T8 | Security / abuse case | yes | AC1–AC5 of `bugfix.md` §Security considerations, one negative test each | `uv run pytest cli/tests/test_api_health_integration.py cli/tests/test_state_root_integration.py -k abuse or security` |
| T9 | Accessibility | n/a — no UI. | | |
| T10 | Migration / upgrade | yes | a config carrying an explicit `state.root: .the-loop` resolves to the **same directory** it resolved to before, when read from the base directory — the "no silent state move" property D1 is built on | `uv run pytest cli/tests/test_state_root_integration.py -k migration` |
| T11 | Manual exploratory | yes | the reporter's repro, end to end: start, `status` from another directory, `curl /health` with and without the poller | recorded under `evidence/manual.md` |
| T12 | Docs parity | yes | `docs/cli/state.md` and `GENERATED_PATHS` still agree; the two schema copies are byte-identical; every new doc page is linked | `uv run pytest cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py cli/tests/test_state_portability.py` |
| T13 | Regression (whole suite) | yes | no existing behaviour moved — in particular nothing that pins a relative `state.root` through a *loaded* config | `make check` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.2, R1.3 | the resolution table: absent → base dir's `.the-loop`; `.the-loop` → the same; `var/state` → `<base>/var/state`; `/srv/x` → verbatim; `~/x` → expanded; a list → warned, default |
| T1 | R1.5 | each spawn site's child environment carries `THE_LOOP_CLI_CONFIG` = the path this process resolved |
| T1 | R2.1, R2.2 | the health status is `degraded` iff some enabled ingress's lock is unheld |
| T1 | R4.2 | `rival_roots` names a candidate holding a heartbeat, skips the resolved root, skips an unreadable directory |
| T2 | R1.4 | `Scenario: one config file, two working directories, one state root` |
| T2 | R1.5 | `Scenario: a spawned service reads the config the CLI resolved, not the one its cwd suggests` |
| T2 | R2.1, R2.3 | `Scenario: health reports degraded, and names the files it is using, when an enabled poller is absent` |
| T2 | R2.2 | `Scenario: health reports ok when every enabled ingress holds its lock` |
| T2 | R3.1, R3.3 | `Scenario: an enabled ingress that cannot start writes an error event, a disabled one writes none` |
| T2 | R3.3 | `Scenario: read.mode poll is a configuration, not a failure` |
| T2 | R2.6, R3.1 | `Scenario: the poller thread dies during startup` |
| T2 | R4.1, R4.2, R4.3 | `Scenario: status names its config, its root and a rival root without changing its exit code` |
| T3 | R2.1, R2.3 | the served `/api/v1/health` schema is the published one |
| T8 | AC1 | `THE_LOOP_CLI_CONFIG` in a spawned child is the parent's resolved path and nothing caller-supplied reaches it |
| T8 | AC3 | the health body carries no pid, token, secret or environment value |
| T8 | AC4 | a degraded health is HTTP 200, so `client.healthy()` still returns `True` and `ensure_service` does not respawn |
| T8 | AC5 | an `ingress.hosted_failed` reason names a missing env **variable**, never its value |
| T10 | R1.2 | `Scenario: an explicit state.root resolves to the directory it always resolved to` |
| T12 | R5.1, R5.2 | the supervision page exists, is linked, and the state page no longer claims a cwd-relative root |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. The API rows use `fastapi.testclient.TestClient`
  against an app built in-process; the lock rows use real `flock` on `tmp_path`, as
  `test_core_daemons.py` does today.
- **Fixtures & data:** `tmp_path`-built config trees (`<tmp>/repo/.the-loop/cli-config.yaml`,
  `<tmp>/home/.the-loop/cli-config.yaml`). No network, no GitHub, no `gh`.
- **Credentials:** none. No row reads a token; the AC5 row asserts on a **variable name**
  (`SLACK_APP_TOKEN`) and never sets a value.
- **Bring-up:** `uv sync` · **Tear-down:** none (`tmp_path` is pytest's).
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T13 | `make check` output: lint, typecheck, unit counts | `verification.md` |
| T2, T3, T10, T12 | the scenario table and the run output | `verification.md` |
| T8 | one section per abuse case: the test, and what it pins | `security-review.md` |
| T11 | the reporter's repro re-run against the fix — `status` from two directories, `curl /health` with the poller absent and present | `manual.md` |

## Verification activities

- [x] T1 — `uv run pytest cli/tests/test_cli_config.py cli/tests/test_state.py cli/tests/test_core_daemons.py cli/tests/test_client.py`
- [x] T2 — `uv run pytest cli/tests/test_state_root_integration.py cli/tests/test_api_health_integration.py`
- [x] T3 — `uv run pytest cli/tests/test_api_contract_parity.py`
- [x] T8 — `uv run pytest cli/tests/test_api_health_integration.py cli/tests/test_state_root_integration.py`
- [x] T10 — `uv run pytest cli/tests/test_state_root_integration.py -k migration`
- [x] T11 — manual: the reporter's repro, recorded in `evidence/manual.md`
- [x] T12 — `uv run pytest cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py cli/tests/test_state_portability.py`
- [x] T13 — `make check`

## Verification results

Executed 2026-09-11 on `claude/github-issue-339-2rj3oh`, base `48d1e8f` (13.11.0).
Every activity ran; none was skipped.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run pytest cli/tests/test_cli_config.py cli/tests/test_state.py cli/tests/test_core_daemons.py cli/tests/test_client.py` | 40 passed | [`verification.md`](evidence/verification.md) |
| T2 | `uv run pytest cli/tests/test_state_root_integration.py cli/tests/test_api_health_integration.py` | 19 passed; both files were red against `48d1e8f` | [`verification.md`](evidence/verification.md) |
| T3 | `uv run pytest cli/tests/test_api_contract_parity.py` | 2 passed | [`verification.md`](evidence/verification.md) |
| T8 | the five abuse cases, one negative test each | 5 of 5 closed | [`security-review.md`](evidence/security-review.md) |
| T10 | `uv run pytest cli/tests/test_state_root_integration.py -k migration` | passed — an explicit `state.root: .the-loop` resolves to the directory it always did | [`verification.md`](evidence/verification.md) |
| T11 | the reporter's repro against a real service on this box | reproduced **and** fixed: `start` exits 1 with `poller failed`, health is `degraded`, `status` from an unrelated directory reports the live poller correctly | [`verification.md`](evidence/verification.md) |
| T12 | `uv run pytest cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py cli/tests/test_state_portability.py` · `npx markdownlint-cli2` | 15 passed; 0 markdown errors | [`verification.md`](evidence/verification.md) |
| T13 | `make check` (ruff, ruff format, pyright, validate_config, pytest) | lint clean, 0 type errors, 7 configs valid, **3366 passed, 1 skipped** | [`verification.md`](evidence/verification.md) |
