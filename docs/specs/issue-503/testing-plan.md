---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#503"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: `read.mode: gateway`

Four kinds of check prove this change: unit tests on the parse, the gates and the status
text; one Gherkin-documented integration test that sends a button press through the
gateway client's dispatch path; abuse-case tests for each boundary in `design.md`
§ Security design; and migration tests. Everything runs in this repository with
`pytest`. Nothing needs Slack or a live gateway.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `SlackChannelConfig` parsing of `gateway`, `push_reachable`, the three gates, the `channels status` lines, the `status` listener row, the `channels listen` refusals | `cd cli && uv run python -m pytest -q tests/test_slack_gateway_read_mode.py` |
| T2 | Integration (scenario) | yes | a `block_actions` press and an approval notification under `mode: gateway`, through `GatewayClientDispatcher` / `dispatch_envelope`, Gherkin-documented | `cd cli && uv run python -m pytest -q tests/test_slack_gateway_read_mode_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API route or payload changes; `/api/v1/gateway` and `/health` keep their shapes | | |
| T4 | End-to-end | n/a — a live run needs a gateway and an instance on a real Slack app. The dispatch path that T2 drives is the same code the gateway client calls, and issue-496's e2e already proved transport delivery | | |
| T5 | UI / visual | n/a — no visual surface; CLI text is covered by T1 | | |
| T6 | Snapshot | n/a — the status lines are asserted by substring in T1, as the existing `channels status` tests do | | |
| T7 | Performance / load | n/a — one extra boolean per config parse | | |
| T8 | Security / abuse case | yes | AC1–AC4: no block → nothing read, no socket, no buttons; a typo → `off`; `channels listen` beside a block refuses before any token is read; no unreceivable button | `cd cli && uv run python -m pytest -q tests/test_slack_gateway_read_mode.py -k abuse` |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | yes | `migrate-config` rewrites `gateway:` + `socket` to `gateway`, is idempotent, leaves configs without a block alone; `needs_migration` flags it; `assert_current` does not refuse it | `cd cli && uv run python -m pytest -q tests/test_migrations.py -k gateway` |
| T11 | Regression (whole suite) | yes | behaviour preserved for every config without `mode: gateway`; the full suite, lint, format, types and markdown | `uv run pre-commit run --all-files` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1 | `gateway` parses and keeps its value when a block is present |
| T1 | R1.2, R1.3 | `enabled_services` gives no listener and `start_watcher` returns `None` under `gateway` |
| T1 | R1.5 | `poll_once` does not skip with `read.mode is 'off'` under `gateway` |
| T1 | R2.1, R2.2, R2.4 | `interactive` / `command_buttons` / `kickoff_picker` are true under `gateway` + grants + block, false without the block, and false under `poll` |
| T1 | R2.3 | the press-time picker check refuses `unpublishable-event` when the block is gone |
| T1 | R4.1 | `socket` + block: listener off, interactivity on |
| T1 | R4.2 | `socket` + block: `channels status` prints the migrate warning; `_start_gateway_client` logs it |
| T1 | R6.1 | `channels status` under `gateway`: `read: gateway`, commands, mentions and shortcuts available, no app-token step |
| T1 | R6.2, R6.3 | `ingress_health` / `start` rows: `off · gateway configured` with a block; the missing-block detail without one |
| T2 | R1.2, R1.4, R2.2 | `Scenario: a button pressed in Slack reaches a gateway-mode instance and is handled` |
| T2 | R1.4 | `Scenario: the gateway client's Slack path classifies a press without checking the read mode` |
| T2 | R2.2, R3.1 | `Scenario: a gateway-mode instance renders Approve / Request changes on an approval notification` |
| T8 | R3.1, R3.2, AC1 | `gateway` with no block → `read_mode == "off"`, an error log naming both keys, no buttons, and the `[!]` line in `channels status` |
| T8 | AC2 | unknown mode → `off` (existing behaviour, re-asserted) |
| T8 | R4.3, AC3 | `run_socket_listener` returns `1` with a block present and with `mode: gateway`, without reading the token variables |
| T8 | R3.3, AC4 | no config except a raw `socket` with no block enables the listener |
| T10 | R5.1–R5.3, R4.4 | rewrite, idempotence, no-block no-op, `needs_migration`, `assert_current` passes |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. Slack and the gateway are faked in-process: a fake
  Slack client and direct calls to `dispatch_envelope` / the client dispatcher, as the
  existing `test_gateway_slack_integration.py` does.
- **Fixtures & data:** in-test config mappings and `tmp_path` state directories.
- **Credentials:** none. Token variables are set to placeholder values with
  `monkeypatch.setenv` where a test needs them present.
- **Bring-up:** `uv sync --locked` · **Tear-down:** none.
- **If bring-up fails:** record it below, leave the dependent activities unticked, and
  escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T8 | pytest summary and red → green note | `unit.md` |
| T2 | scenario table (`the-loop scenarios`) and run output | `integration.md` |
| T10 | pytest output, plus a `migrate-config --dry-run`-style before/after on a sample config | `migration.md` |
| T11 | pre-commit summary | `lint-and-typecheck.md` |

## Verification activities

- [x] T1 — `cd cli && uv run python -m pytest -q tests/test_slack_gateway_read_mode.py`
- [x] T2 — `cd cli && uv run python -m pytest -q tests/test_slack_gateway_read_mode_integration.py`
- [x] T8 — `cd cli && uv run python -m pytest -q tests/test_slack_gateway_read_mode.py -k abuse`
- [x] T10 — `cd cli && uv run python -m pytest -q tests/test_migrations.py -k gateway`
- [x] T11 — `uv run pre-commit run --all-files`

## Verification results

All five activities ran and passed. The new tests are red on `origin/main` (23 of 40) and
green here. Every command ran with `THE_LOOP_CLI_CONFIG` unset, because a the-loop session
exports it pointing at the operator's live config, and inherited, it skews unrelated tests
(see [unit.md](evidence/unit.md)).

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `cd cli && uv run python -m pytest -q tests/test_slack_gateway_read_mode.py` | 37 passed. On `origin/main`: 23 failed, 17 passed | [unit.md](evidence/unit.md) |
| T2 | `cd cli && uv run python -m pytest -q tests/test_slack_gateway_read_mode_integration.py`; `the-loop scenarios --glob …` | 3 passed. 3 scenarios listed with requirement links. The Approve-pair scenario is red on main | [integration.md](evidence/integration.md) |
| T8 | `… tests/test_slack_gateway_read_mode.py -k abuse` | 13 passed (AC1–AC4) | [unit.md](evidence/unit.md) |
| T10 | `… tests/test_migrations.py -k gateway`; `the-loop migrate-config --dry-run`, then two real runs on a sample 20.3.0 config; `channels status` before and after | 6 passed. Rewritten `socket → gateway`, and the second run reports nothing to migrate. Status flags the old form and describes the new one | [migration.md](evidence/migration.md) |
| T11 | `uv run pre-commit run --all-files` | All six hooks passed (ruff ×2, pyright, the full pytest suite, markdownlint, config validation) | [lint-and-typecheck.md](evidence/lint-and-typecheck.md) |

## Review comments
