---
type: testing-plan
phase: test-planning
workItem: "issue-322"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: instances scoped to their own work items

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `instance.py`: `InstanceConfig.from_mapping` (defaults, the name grammar, the three modes, unknown mode → locked, addressed-without-name → locked, declared refs and URLs, a bad entry skipped by index, a non-mapping block); `parse_address` (whole-token, prefix case, the grammar, several tokens, two different names → ambiguous, malformed → no address); `decide` (the seven-row table); `apply_instance` fan-out and `RoutingConfig.instance`; `ControlRecord.instance` round trip; `command_comment(address=)`; `announcement_body(instance=)`; `TmuxRunner.spawn_in` argv with and without a name and with an old tmux; `describe_instance`; the `status` line | `uv run --project cli python -m pytest -q cli/tests/test_instance.py cli/tests/test_control.py cli/tests/test_announce.py cli/tests/test_lifecycle_cmd.py` |
| T2 | Integration (scenario) | yes | Gherkin scenarios over two real dispatchers fed one event stream: an addressed start reaches one instance; an unaddressed start on two addressed instances reaches neither and is recorded; a locked instance refuses an address but takes a declared item; a managed item's events are delivered in every mode; an open unnamed instance is 13.3.1; `sessions start` on a locked instance is refused and on an addressed one claims; the poll ingress honours the token | `uv run --project cli python -m pytest -q cli/tests/test_instance_integration.py` |
| T3 | Contract (OpenAPI) | yes | `GET /api/v1/instance` in the authored contract and served identically; the router carries it; the MCP registry lists it as a read tool | `uv run --project cli python -m pytest -q cli/tests/test_api_contract_parity.py cli/tests/test_mcp_integration.py` |
| T4 | End-to-end | n/a — the dispatchers are exercised in-process with `FakeTmux`; a real spawn needs tmux and a harness binary | | |
| T5 | UI / visual | n/a — the Settings tab renders the block from the schema, as every block | | |
| T6 | Snapshot | n/a — field assertions on small dataclasses and dicts | | |
| T7 | Performance / load | n/a — one registry read and one record read per refused event, both already made for an accepted one | | |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A6 (`design.md` § Security design) | `uv run --project cli python -m pytest -q cli/tests -k "unauthorized_address or malformed_token or does_not_unlock or unknown_mode_resolves or leaves_no_mark or only_the_configured_name"` |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | yes | a config without `instance` is unnamed and open and every existing dispatcher test passes unchanged; a config with the block validates against the authored schema and the packaged copy is byte-identical; `CURRENT_CONFIG_VERSION` unchanged; a pre-issue-322 control record reads as unnamed; the docs↔schema and SDK↔docs parity tests pass | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_sdk_docs_parity.py cli/tests/test_migrations.py cli/tests/test_control_integration.py cli/tests/test_graphlink_integration.py` and `make validate` |
| T11 | Manual exploratory | n/a — the reviewer's walk-through is the PR briefing's "what to check" | | |
| T12 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T13 | Security review (gate) | yes | the-loop checklist against A1–A6, recorded as evidence; tier 4 needs a **named human sign-off** (`humanSignOffMinTier: 4`) — the owner's, at the PR | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.2, R1.4, R1.5 | the block parses; unset is unnamed/open; bad name, bad mode, bad entry, addressed-without-name |
| T1 | R3.1, R3.3, R3.4 | the token grammar; two names ambiguous; malformed is no address |
| T1 | R2.1–R2.4, R3.2 | the decision table, row by row |
| T1 | R4.1, R4.2, R4.3, R4.6 | the record field; the posted keyword; the announcement row; the tmux argv |
| T1 | R4.4, R4.5 | `describe_instance`; the status line and JSON |
| T2 | R2.1–R2.7, R3.1–R3.5, R4.1 | `Scenario: An addressed start reaches only the instance it names` and siblings |
| T3 | R4.4 | contract parity; the MCP tool list |
| T8 | A1–A6 | one negative test each, named in `design.md` § Security design |
| T10 | R1.2, R1.3, R5.1 | schema parity, docs parity, no migration, existing suites unchanged |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. Dispatchers run with `FakeTmux`, a no-op reactor,
  announcer and verifier (the suite's autouse fixtures); the service is exercised with
  FastAPI's test client; nothing binds a port.
- **Fixtures & data:** temp directories per test; two dispatchers share nothing but the
  event objects they are handed.
- **Credentials:** none.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T3, T8, T10, T12 | command, counts, duration, raw tail of the output; red → green per task | `verification.md` |
| T13 | the abuse-case table with verdicts and the tests that close each; the sign-off line | `security-review.md` |

## Verification activities

- [ ] T1 — `uv run --project cli python -m pytest -q cli/tests/test_instance.py cli/tests/test_control.py cli/tests/test_announce.py cli/tests/test_lifecycle_cmd.py`
- [ ] T2 — `uv run --project cli python -m pytest -q cli/tests/test_instance_integration.py`
- [ ] T3 — `uv run --project cli python -m pytest -q cli/tests/test_api_contract_parity.py cli/tests/test_mcp_integration.py`
- [ ] T8 — `uv run --project cli python -m pytest -q cli/tests -k "unauthorized_address or malformed_token or does_not_unlock or unknown_mode_resolves or leaves_no_mark or only_the_configured_name"`
- [ ] T10 — `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_sdk_docs_parity.py cli/tests/test_migrations.py cli/tests/test_control_integration.py cli/tests/test_graphlink_integration.py` and `make validate`
- [ ] T12 — `make check`
- [ ] T13 — `evidence/security-review.md`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |

**Not executed:** —

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
