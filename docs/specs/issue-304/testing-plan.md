---
type: testing-plan
phase: test-planning
workItem: "issue-304"
status: locked
approvedBy: []
overrides: {}
---

# Testing plan: one Slack surface, two identity allow-lists

> Derived from the locked `requirements.md` and `design.md`, **before** `tasks.md`.
> Authored at `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit — schema refusal (collaborators) | yes | a collaborator carrying `notifications` fails validation, and the message names `channels.slack` **and** `the-loop migrate-config`; a collaborator with only `handle`/`kind`/`roles` still validates | `cd cli && uv run pytest tests/test_configschema.py` |
| T2 | Unit — schema refusal (cli-config) | yes | a config carrying top-level `collaborators` or `notifications` fails validation with the same guidance; neither key remains a schema leaf | `cd cli && uv run pytest tests/test_configschema.py` |
| T3 | Unit — migration round trip | yes | a 0.5.0 config with both blocks migrates to a clean 0.6.0 config; a second run reports no change and produces byte-identical YAML; every neighbouring key survives untouched (A3) | `cd cli && uv run pytest tests/test_migrations.py` |
| T4 | Unit — the runtime refusal | yes | `assert_current` refuses a config still declaring either block, **including one that claims `version: 0.6.0`** (A1, A2), naming the key and the fix | `cd cli && uv run pytest tests/test_migrations.py` |
| T5 | Unit — the allow-lists are untouched | yes | `routing.authorizedUsers` and `channels.slack.authorizedUsers` are still schema leaves after the removal and still validate a real value (T1 of the threat model, R2.4) | `cd cli && uv run pytest tests/test_configschema.py` |
| T6 | Regression — channels | yes | the whole channel suite, unchanged: `ask` fan-out, the `notify` hook's gate on `harness-config.yaml → notifications.events`, the reply pipeline | `cd cli && uv run pytest tests/test_channels.py tests/test_channels_integration.py tests/test_standing_channels_integration.py` |
| T7 | Regression — harness config read surface | yes | the pinned read-surface test still passes: `notifications` stays a harness-config key and the harness side is not collaterally trimmed (R2.5) | `cd cli && uv run pytest tests/test_harness_config.py` |
| T8 | Drift — schema/docs parity | yes | P3 (no doc heading for a removed key), P4 (no schema leaf undocumented), the `.the-loop/` ↔ `the_loop/schemas/` byte parity, the manifest/scaffolded-config assertions, and the validator's keyword guard + jsonschema differential | `cd cli && uv run pytest tests/test_docs_parity.py tests/test_config_schema_parity.py tests/test_manifest_schemas.py tests/test_configschema.py` |
| T9 | Contract validation — the shipped configs | yes | every config this repo ships (`.the-loop/*.yaml`, both templates, the packaged harness default) validates against its schema under real `jsonschema` | `make validate-config` / `python3 scripts/validate_config.py` |
| T10 | Doc grep — no unbacked promise | yes | `grep -ri "channel-list" docs/ skills/` returns no hit promising per-collaborator delivery; the "delivered on each recipient's enabled channels" sentence is gone (R4.2) | manual grep, recorded in the evidence file |
| T11 | Lint / typecheck / full suite | yes | the commands CI runs, at the pinned versions | `cd cli && uv run ruff check . && uv run pyright && uv run pytest`; `markdownlint` on every doc touched |
| T12 | Integration / end-to-end | n/a — no ingress, dispatch, session or channel code path is modified; the retired blocks had no reader to exercise end-to-end | | |
| T13 | UI / visual / accessibility | n/a — no UI surface reads either block, and the control-plane form renders the schema it is served (covered by T2's leaf assertions) | | |
| T14 | Performance | n/a — one dict lookup on an already-failing validation path; the migration adds two `pop`s to a command an operator runs once | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1 | `notificationChannel` and `collaborator.notifications` are gone from the loaded schema |
| T1 | R1.2 | a collaborator carrying `notifications` is refused, and the message names both the replacement and the command |
| T1 | R1.3 | `handle` / `kind` / `roles` still validate a real collaborator |
| T2 | R2.1 | neither `collaborators` nor `notifications` is a leaf of the CLI config schema |
| T2 | R2.2 | a config declaring either is refused with guidance |
| T3 | R3.1, R3.2 | 0.5.0 + both blocks → clean 0.6.0, both removals reported |
| T3 | R3.3 | second run: `changed is False`, identical YAML |
| T3 | R3.4, A3 | a non-empty block produces the `channels.slack` note; every other key survives |
| T4 | A1 | a config claiming 0.6.0 while carrying `collaborators` is still refused |
| T4 | A2 | the refusal names the key — nothing is silently dropped |
| T5 | R2.4, T1 | both identity allow-lists still resolve and validate |
| T6 | R2.3, NFR2 | `channels.slack` behaviour unchanged |
| T7 | R2.5, NFR1 | `harness-config.yaml → notifications.events` still gates `notify` |
| T8 | NFR1, R4.1 | schemas, docs and shipped configs agree |
| T9 | R4.1 | every shipped config validates with the retired shapes gone |
| T10 | R4.2, R4.3, R4.4 | no doc promises per-collaborator delivery; the capability history records the change |

## Results

Full evidence in [`evidence/verification.md`](evidence/verification.md). Every applicable
row passed: **2679 → 2698** tests (nineteen added, none removed or weakened), ruff +
`ruff format --check` + pyright clean, markdownlint clean over 876 docs, all seven shipped
configs `VALID` under real `jsonschema`, and every new test seen to fail against the
unfixed tree first (15 failures, no pre-existing test disturbed).

## Verification environment

The repository checkout itself: `cli/` under `uv` with the lockfile's pinned versions, and
`python3 scripts/validate_config.py` for the jsonschema pass. No daemon is started, no
network is used, and no Slack token is needed — every test in the matrix is a pure
filesystem or in-process check.

## Evidence to capture

- Full `pytest` output (before → after test counts), `ruff`, `pyright`.
- `python3 scripts/validate_config.py` output for all six shipped configs.
- The `migrate-config --dry-run` report on a 0.5.0 fixture, and the second run's
  "nothing to migrate".
- The T10 grep output.
- Redaction: none of the above carries a token, a secret, or a path outside the checkout.

## Activities checklist

- [x] Every new test run against the **unfixed** tree first, and seen to fail there.
- [x] The full suite green after.
- [x] Shipped configs validated with real `jsonschema`, not only the hand-rolled validator.
- [x] Docs grepped, capability history row added.
