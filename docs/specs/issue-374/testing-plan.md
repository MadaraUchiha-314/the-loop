---
type: testing-plan
phase: test-planning
workItem: "issue-374"
status: approved
approvedBy: [MadaraUchiha-314]   # PR #436 review, 2026-09-29: "go ahead with implementation."
overrides: {}
---

# Testing plan: a manager instance over many instances of the-loop

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `instance.py`: `role` and `manager` parsing, the registry validation by index (grammar, duplicate, scheme, userinfo, self), the two boot refusals under `strict=True` and the warn-and-`worker` reading otherwise; `manager/fleet.py`: probe states and transitions (`live`/`unreachable`/`mismatched`, once-per-transition events), the cache and its interval, the bounded fan-out with a hung member, `by_instance`/`by_ref`/`by_standing_name` (one, none, several, explicit `instance`), member error translation (400/404/409/other/transport); `manager/facade.py`: one test per row of design § 4 (stamping, ordering, the header, `instance` required, own-vs-proxied); `manager/stream.py`: the cursor grammar, per-member resume, stamping, `desync`, backoff, keep-alive loss; `core/instances.py`: the worker self row, `register`/`unregister` through `update_config` (file byte-identical on refusal), the worker's `400`; `commands/instances.py`: `list` (table and `--json`), `register`/`unregister` exit codes and messages, routed through the service and via the local seam; `core.instance.assert_self`; `_restart_required` for `instance.role`; `status_all` and the `status` lines on a manager | `uv run --project cli python -m pytest -q cli/tests/test_instance.py cli/tests/test_manager_fleet.py cli/tests/test_manager_facade.py cli/tests/test_manager_stream.py cli/tests/test_instances_core.py cli/tests/test_instances_cmd.py cli/tests/test_lifecycle_cmd.py cli/tests/test_api_config_integration.py` |
| T2 | Integration (scenario) | yes | Gherkin scenarios over two worker apps and one manager app in one process (injected transport): a list read is the union with each row's `instance`; a keyed read routes to the member that manages the ref; an ambiguous ref is refused and sent to neither; a member going away degrades health, sets the header, and recovers; a registration through the API equals a hand edit of the file and is live on the next request; a mismatched member is served from nowhere; `instance` on a worker is accepted only for itself; a proxied config write lands on the member's file and in both event logs; the manager's own work items appear beside its members' under its own name, and an operation without `instance` reaches the manager's own state. One socket-level scenario with real `uvicorn` processes on ephemeral loopback ports: the manager's stream fans in two members' frames and resumes each from its own cursor | `uv run --project cli python -m pytest -q cli/tests/test_manager_integration.py cli/tests/test_manager_stream_integration.py` |
| T3 | Contract (OpenAPI) | yes | the authored contract carries `instances`, `instances/register`, `instances/unregister` and the `instance` parameter on the 30 operations of design § 4; the served schema matches it for **both** a worker app and a manager app (the parity test parameterised over the role); the MCP tool list is identical on both roles and gains `list_instances` only; the SDK docs list `loop.instances()` | `uv run --project cli python -m pytest -q cli/tests/test_api_contract_parity.py cli/tests/test_mcp_integration.py cli/tests/test_sdk_docs_parity.py` |
| T4 | End-to-end | n/a — the socket-level stream scenario in T2 is the one journey that needs real processes; everything else is exercised in-process against the same code | | |
| T5 | UI / visual | yes | vitest: the route parser (`#/item/<ref>@<instance>`, `#/instances`, `#/instances/<name>`, every legacy hash unchanged), the client sending `instance` only when set, the board keyed by `instance@ref` with a duplicate ref as two rows, the sidebar filter and chip, `healthTone` folding the fleet, the Instances and InstanceDetail views (worker and manager documents; every control disabled when not `live`; the Register card's client-side validation); screenshots of the five prototype states in light and dark compared by eye with the locked artifact | `cd ui && bun run test` · screenshots via Playwright against `bun run preview` |
| T6 | Snapshot | n/a — field assertions on small documents; the contract test is the schema's snapshot | | |
| T7 | Performance / load | yes, bounded | a list read against 8 in-process members with one hung member completes within `timeoutSeconds + 1 s`; a manager with 8 subscribers holds exactly N upstream connections for N live members | `uv run --project cli python -m pytest -q cli/tests/test_manager_fleet.py -k "bounded or upstream_count"` |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A9 (`design.md` § Security design), each named there | `uv run --project cli python -m pytest -q cli/tests -k "foreign_url or mismatched_member or malformed_member or hung_member or ambiguous_ref or unknown_instance or foreign_instance or proxied_write or worker_half_is_unchanged or overwrites_a_members_claim"` |
| T9 | Accessibility | yes, light | the state word beside every dot, the native `<select>` filter, buttons for every action, focus order through the Register card and the table — asserted in the vitest render tests and checked by hand on the prototype | `cd ui && bun run test -- Instances` |
| T10 | Migration / upgrade | yes | a config without `role` is a worker and every existing dispatcher, service and dashboard test passes unchanged; a config with the block validates against the authored schema and the packaged copy is byte-identical; `CURRENT_CONFIG_VERSION` unchanged; a 19.14.1 member (no `role` in its `/instance` document) probes as `live`; the docs↔schema parity test passes; the dashboard's stored settings are read unchanged | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_migrations.py cli/tests/test_instance_integration.py cli/tests/test_api_routers_integration.py` and `make validate` and `cd ui && bun run test -- settings` |
| T11 | Manual exploratory | yes | two workers and a manager on one machine (three configs, three ports), the hosted dashboard pointed at the manager: the board shows both workers' items with chips, the filter narrows, a `the-loop start` on one worker appears on the board, a reply from the composer lands in that worker's pane, the Instances tab registers a third URL and shows it `unreachable` until started, Manage edits a worker's config and the worker's `status` shows the change; the procedure recorded as evidence | procedure in `evidence/manual.md` |
| T12 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` and `cd ui && bun run lint && bun run typecheck && bun run build` |
| T13 | Security review (gate) | yes | the-loop checklist against A1–A9, recorded as evidence; tier 4 needs a **named human sign-off** — the owner's, at the PR | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.2, R1.5, R1.6 | the block parses; unset is a worker; unknown role and unnamed manager refuse at boot, warn elsewhere; a bad entry skipped by index |
| T1 | R1.4 | `instance.role` in `restartRequired`; a registry edit is read on the next request |
| T1 | R2.2–R2.7, R2.9 | the facade table, row by row; the header; own-vs-proxied |
| T1 | R2.8 | the cursor grammar; per-member resume; one `desync`; the stamp |
| T1 | R3.1, R3.3, R3.4 | the self row; the manager rows; the `status` lines; the transition events |
| T1 | R4.2–R4.4, R4.6 | register/unregister write through the splice; validation; the worker's refusal; the CLI verbs' rendering and exit codes |
| T1 | R6.1–R6.4 | the name and role check; the overwritten stamp; the bounded, shape-checked read |
| T2 | R2.2–R2.9, R3.1, R4.1–R4.3, R6.1 | `Scenario: A list read on the manager is the union of its live members` and siblings, named in the test file |
| T3 | R2.1, R3.2, R4.5, R7.3 | contract parity on both roles; the tool lists; the SDK docs |
| T5 | R5.1–R5.6 | the route parser; the client; the board key; the chip and filter; the two views; the demo row |
| T7 | NFR latency, R2.8 | one hung member; the upstream count |
| T8 | A1–A9 | one negative test each, named in `design.md` § Security design |
| T10 | R1.2, R7.1 | schema parity, docs parity, no migration, existing suites unchanged, a 19.14.1 member |
| T11 | R5.1–R5.4, R4.2 | the walk-through |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none for T1–T3, T5–T10: workers and the manager run as
  FastAPI test clients in one process, joined by the injected transport; nothing binds a
  port. T2's stream scenario and T11 start `uvicorn` processes on ephemeral loopback
  ports (`the-loop start` with three temporary configs under a temp state root) and stop
  them in a fixture finaliser; `tmux` is not needed (no session is spawned).
- **Fixtures & data:** temp directories per test, one config and one state root per
  instance; portable records seeded by writing files, as the existing service tests do.
- **Credentials:** none.
- **Bring-up:** `uv sync` and `cd ui && bun install` · **Tear-down:** the fixtures' own.
- **If bring-up fails:** record it under Verification results and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T3, T7, T8, T10, T12 | command, counts, duration, raw tail of the output; red → green per task | `verification.md` |
| T5, T9 | vitest summary; screenshots of the five states, light and dark, from the locked prototype and from the built app | `verification.md`, `ui/<state>-<theme>.png` |
| T11 | the procedure and what each step showed, redacted | `manual.md` |
| T13 | the abuse-case table with verdicts and the tests that close each; the sign-off line | `security-review.md` |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_instance.py cli/tests/test_manager_fleet.py cli/tests/test_manager_facade.py cli/tests/test_manager_stream.py cli/tests/test_instances_core.py cli/tests/test_lifecycle_cmd.py cli/tests/test_api_config_integration.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_manager_integration.py cli/tests/test_manager_stream_integration.py`
- [x] T3 — `uv run --project cli python -m pytest -q cli/tests/test_api_contract_parity.py cli/tests/test_mcp_integration.py cli/tests/test_sdk_docs_parity.py`
- [x] T5 — `cd ui && bun run test` and the screenshot capture
- [x] T7 — `uv run --project cli python -m pytest -q cli/tests/test_manager_fleet.py -k "bounded or upstream_count"`
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests -k "foreign_url or mismatched_member or malformed_member or hung_member or ambiguous_ref or unknown_instance or foreign_instance or proxied_write or worker_half_is_unchanged or overwrites_a_members_claim"`
- [x] T9 — `cd ui && bun run test -- Instances`
- [x] T10 — `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_migrations.py cli/tests/test_instance_integration.py cli/tests/test_api_routers_integration.py` and `make validate` and `cd ui && bun run test -- settings`
- [x] T11 — the procedure in `evidence/manual.md`
- [x] T12 — `make check` and `cd ui && bun run lint && bun run typecheck && bun run build`
- [x] T13 — `evidence/security-review.md`

## Verification results

Executed 2026-09-30 at the `verification` node; the full record is
[`evidence/verification.md`](evidence/verification.md).

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | the eight unit files | 147 passed | `evidence/verification.md` § T1 |
| T2 | the two in-process scenario files and the socket-level one | 15 passed | § T2 |
| T3 | contract parity over both roles, the MCP tool list, the SDK docs | 15 passed | § T3 |
| T5 | `bun run test`; screenshots of the built bundle against a live manager | 324 passed; 8 screenshots | § T5, `evidence/ui/` |
| T7 | `-k "hung_member or upstream_per_live_member"` | 2 passed | § T7 |
| T8 | the abuse-case selection | 13 passed | § T8, `evidence/security-review.md` |
| T9 | the render tests' assertions and the prototype by hand | pass | § T5 / T9 |
| T10 | schema, docs, migrations, the issue-322 suites, the routers, the event catalogue | 104 passed | § T10 |
| T11 | three real services on one machine | pass | `evidence/manual.md` |
| T12 | ruff, ruff format, pyright, markdownlint, validate, the CI-form suite | all clean; 4965 passed, 1 skipped | § T12 |
| T13 | the security review gate | see the record | `evidence/security-review.md` |

**Not executed:** none. `make validate` and `make test` ran through their underlying
commands because the container's `uv` predates the Makefile's pin (§ T12).

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
