---
type: testing-plan
phase: test-planning
workItem: issue-222
status: draft                # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: the CLI config is editable from the Control Plane UI

> Derived from the approved `requirements.md` and `design.md`, **before** `tasks.md`.
> Authored at the `test-planning` node and **completed at the `verification` node**.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. No credentials of any kind are involved: every command below runs a test
> suite or a linter over this repository, against temp directories.

## What this work item has to prove

Three claims carry the risk, and each gets its own kind of test rather than a shared
"it works":

1. **A save does not damage the file.** Text-level splicing is the one novel mechanism
   here, so it is tested against the real, heavily commented shipped template — comment
   count, byte-for-byte equality of every untouched line, and a property-style round trip
   over many key paths — not against a three-line fixture that would pass whatever we
   wrote.
2. **An invalid config never reaches disk.** Every rejection path is asserted *twice*: the
   response is 400, **and** the file is byte-identical to what it was.
3. **The validator is not a comforting stub.** It is compared against real `jsonschema`
   (a dev dependency) over a corpus, and a keyword guard fails if the schema grows a
   construct it does not implement.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit — `yamlpatch` | yes | splice fidelity and comment preservation: existing scalar, block sequence, flow sequence, empty container, missing leaf, missing parent chain, a `null` leaf that removes a key, absent file; every untouched byte of the shipped template survives; an unverifiable splice raises rather than returning text (R2.1–R2.4, R2.8) | `uv run pytest cli/tests/test_yamlpatch.py` |
| T2 | Unit — `configschema` | yes | `$ref` resolution against the packaged collaborators schema; type/enum/range/unknown-key violations are reported with their key path; the keyword guard; **differential agreement with `jsonschema`** over valid and invalid corpora (R3.1, NFR4) | `uv run pytest cli/tests/test_configschema.py` |
| T3 | Unit — `core.config` | yes | read of a missing file, a present file and an unparseable file; merge + changed-path computation; `restartRequired` selection; atomic write leaves no temp file; failure paths leave the file byte-identical (R1.1–R1.5, R2.5, R2.7, R3.4, R3.5, R4.4, R4.5) | `uv run pytest cli/tests/test_core_config.py` |
| T4 | Integration — the three routes | yes | `GET /config`, `GET /config/schema`, `POST /config` through FastAPI's `TestClient` against a temp config: 200/400 mapping, the CORS pairing refusal, the migration-gate refusal, the event-log record naming key paths and not values (R1, R2, R3, security design) | `uv run pytest cli/tests/test_api_config_integration.py` |
| T5 | Integration — hot reload | yes | a `POST` is visible to the *next* request without a restart; a `Reloader` baselined on the file — the one the poller and receiver hold — rebuilds after an API write; a hand-edit is picked up too; a file that becomes unparseable keeps the previous config (R4.1, R4.2, R4.3) | `uv run pytest cli/tests/test_api_config_integration.py` |
| T6 | Contract (OpenAPI) | yes | the three operations are authored in `docs/api-specs/openapi/the-loop.v1.yaml` and the served schema matches it exactly (NFR3) | `uv run pytest cli/tests/test_api_contract_parity.py` |
| T7 | Parity — packaged schema | yes | `the_loop/schemas/*.json` are byte-identical to `.the-loop/*.schema.json`, and resolve from the package with no repository checkout (design §Where the schema comes from) | `uv run pytest cli/tests/test_config_schema_parity.py` |
| T8 | Unit — UI field model | yes | `fieldsOf` derives sections and leaf kinds from the schema (string/number/boolean/enum/string-array/structured); `getIn`/`setIn`; `diff` emits a sparse patch and nothing for an unchanged draft (R5.1–R5.4, R5.6) | `cd ui && bun run test` |
| T9 | UI / component render | yes | the editor renders a section per top-level property with the schema's prose, an unset field shows its default as a placeholder rather than a value, an unsupported subtree renders a structured field, and Save posts the diff (R5.1, R5.5, R5.6); demo mode renders with no network call (R5.7) | `cd ui && bun run test` |
| T10 | Security / abuse case | yes | the five abuse cases: no request field names a path; a write emits key paths and no values; the un-bootable CORS pairing is refused at write time; every rejection leaves the file untouched; no schema key holds a secret | asserted in T3/T4 + review against `requirements.md` §Security considerations |
| T11 | Accessibility | yes, partial | every control has a programmatic label and its description is associated with it; the structured field reports a parse error in text, not colour alone | assertion in T9 (`getByLabelText`) + manual read-through; no axe run — the repo has no accessibility harness, and adding one is its own work item |
| T12 | Snapshot | n/a — the one byte-exact comparison that matters (the template survives a save) is an explicit assertion in T1, which says *what* must not change; a snapshot would only say *that* something did | | |
| T13 | Performance / load | n/a — one `sha256` of a ~10 KB file per API request, and one file write per save. No load dimension; the cost is stated in `design.md` rather than measured | | |
| T14 | Migration / upgrade | yes | an operator's existing config keeps working: `assert_current` still gates reads, and a config below `CURRENT_CONFIG_VERSION` is refused by the write path with the message that names the fix (R3.2) | assertion in T3/T4 + `uv run python scripts/validate_config.py` |
| T15 | End-to-end | n/a — `cli/tests/test_pdlc_e2e/` drives the *process graph* against a mocked harness; config editing is not a graph node and has no place in that suite | | |
| T16 | Manual exploratory | yes | run `the-loop service start` against a copy of the shipped config, open the built UI, change a value, confirm the file changed and kept its comments. The **daemon** side is not run by hand — no poller or receiver is started in this session; R4.1 is carried by T5's reloader assertion instead, and this row says so rather than implying a run that did not happen | recorded in evidence with the diff of the touched file |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R2.1, R2.2 | `Scenario: a save rewrites one value and leaves every comment` |
| T1 | R2.3 | `Scenario: a key absent from the file is inserted under its parent` |
| T1 | R2.4 | `Scenario: a config file that does not exist is created with its modeline` |
| T1 | R2.6 | `Scenario: a patch leaf of null removes the key` (in the shape-parametrised case) |
| T1 | R2.8 | `Scenario: a splice that does not re-parse to the intended document raises` |
| T2 | R3.1 | `Scenario: an unknown key, a wrong type and an out-of-enum value are each named` |
| T2 | NFR4 | `Scenario: the packaged schema resolves with no repository checkout` |
| T3 | R1.1, R1.2 | `Scenario: a workstation with no config file reads as empty, not as an error` |
| T3 | R1.5 | `Scenario: an unparseable config is an error, not an empty config` |
| T3 | R2.5, R2.7 | `Scenario: an empty patch writes nothing` / `Scenario: the write is atomic` |
| T3 | R3.5 | `Scenario: a refused save leaves the file byte-identical` |
| T3 | R4.4, R4.5 | `Scenario: a bind change is reported as restart-required, a routing change is not` |
| T4 | R1.3, R3.1–R3.3 | `Scenario: the schema route serves a resolved schema` / `Scenario: the un-bootable CORS pairing cannot be saved` |
| T4 | security design | `Scenario: a config write is recorded as key paths, never values` |
| T5 | R4.1 | `Scenario: a daemon watching the file sees a saved change` |
| T5 | R4.2, R4.3 | `Scenario: a saved change is live on the next request` / `Scenario: a hand-edit is picked up too` |
| T6 | NFR3 | existing: `Scenario: the served schema drifts from the authored contract` |
| T7 | design §schema home | `Scenario: the packaged schema is the authored schema` |
| T8, T9 | R5.1–R5.7 | `sections mirror the schema` · `an unset field offers its default` · `an unsupported subtree stays editable` · `save sends only what changed` |
| T14 | R3.2 | `Scenario: a config below the current version is refused with the upgrade command` |

## Verification environment

- **Repositories:** this one. The API tests point a whole app at a `tmp_path` config, so
  no test reads or writes the operator's real `~/.the-loop/cli-config.yaml` or this
  repository's `.the-loop/cli-config.yaml`.
- **Services / containers:** none for T1–T15. T16 runs `the-loop service start` on
  loopback in this checkout.
- **Fixtures & data:** `skills/the-loop/templates/cli-config.yaml` is used as the
  realistic input for T1 (it is the file operators actually have); `tmp_path` for
  everything else.
- **Credentials:** none. No token, secret or environment variable is read by any test.
- **Bring-up:** `uv sync`; `cd ui && bun install`.
- **Tear-down:** none (temp dirs are pytest's).
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate — an activity that could not run is never ticked.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1–T7, T14 | pytest output per row plus the full suite (counts, duration) | `verification.md` |
| T8, T9, T11 | vitest output; the rendered editor | `verification.md`, `settings-config.png` |
| T16 | the before/after diff of the touched config file, showing the changed value and the surviving comments | `verification.md` |
| all | quality gates: `make lint`, `make format-check`, `make typecheck`, `make validate`, UI `typecheck`/`lint` | `verification.md` |

Redaction: T16's diff is of a config in this public repository and holds no secret; any
absolute path that would reveal a home directory is replaced with `~`.

## Verification activities

- [x] T1 — `uv run pytest cli/tests/test_yamlpatch.py`
- [x] T2 — `uv run pytest cli/tests/test_configschema.py`
- [x] T3 — `uv run pytest cli/tests/test_core_config.py`
- [x] T4, T5, T10 — `uv run pytest cli/tests/test_api_config_integration.py`
- [x] T6 — `uv run pytest cli/tests/test_api_contract_parity.py`
- [x] T7 — `uv run pytest cli/tests/test_config_schema_parity.py`
- [x] T8, T9, T11 — `cd ui && bun run test`
- [x] T14 — `uv run python scripts/validate_config.py`
- [x] full suite — `make test`
- [x] quality gates — `make lint format-check typecheck validate` + `cd ui && bun run typecheck && bun run lint`
- [x] T16 — manual: service + UI, edit a value, inspect the file and the daemon
