---
type: testing-plan
phase: test-planning
workItem: "issue-309"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: one event bus, many channels, one ledger

> Derived from the approved `requirements.md` and `design.md`, before `tasks.md`.
> Authored at `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | catalog views; `Principal` parsing; envelope stamp/parse; `render_blocks`; classification order; grant filtering; `SlackChannelConfig` defaults and refusals; `GitHubLedger` record shapes against a fake `gh` | `uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_identity.py cli/tests/test_bus.py` |
| T2 | Integration (scenario) | yes | the eight Gherkin scenarios below through the real modules with the SDK client, the `gh` writer and `reply_session` faked | `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py cli/tests/test_bus_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API route changes; the control plane's `/config` still serves the schema, whose parity test is T10 | | |
| T4 | End-to-end | n/a — needs a Slack workspace and a live `gh`; the integration rows fake exactly those two boundaries and nothing else | | |
| T5 | UI / visual | n/a — the Block Kit payload is asserted structurally (T1); no rendered UI is produced by this repository | | |
| T6 | Snapshot | n/a — one Block Kit shape per event type is asserted field by field, which is stricter than a snapshot and survives a reorder | | |
| T7 | Performance / load | n/a — the kickoff read adds one `conversations.history` call per cycle, bounded by the poll interval | | |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A10 (`design.md` § Security design) | `uv run --project cli python -m pytest -q cli/tests -k "abuse or unauthorized or envelope or grant or kickoff"` |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | yes | 0.6.0 → 0.7.0: refusal of the removed keys naming the fix; `events → subscribe`; Slack ids → `routing.authorizedUsers` entries; idempotence; schema parity (`.the-loop/` vs packaged) | `uv run --project cli python -m pytest -q cli/tests/test_migrations.py cli/tests/test_config_schema_parity.py cli/tests/test_configschema.py` |
| T11 | Manual exploratory | n/a — the reviewer's walk-through is the PR briefing's "what to check"; nothing here needs a human at a keyboard to be proven | | |
| T12 | Lint / format / typecheck / config validation | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T13 | Security review (gate) | yes | the harness's review against A1–A10, recorded as evidence; the named human sign-off tier 4 requires is requested in the PR | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.2, R1.5 | the catalog's four views agree; the docs table lists every subscribable event |
| T1 | R5.1, R5.2, R5.5 | strings and mappings parse; a malformed entry is dropped with a warning; `github_logins` is what the router sees |
| T1 | R3.2, R3.7 | the envelope round-trips and rejects anything but its own shape |
| T1 | R4.2, R4.3, R4.5 | block shapes per event; action buttons only in socket mode with the grant |
| T1 | R2.3, R2.4, R2.5 | classification order; a grant outside the publishable set is ignored with a warning |
| T2 | R1.3, R1.4, R3.3 | `Scenario: An asked question is one ledger comment and one Slack post` |
| T2 | R6.1, R3.7 | `Scenario: An agent's comment reaches the Slack thread and a human's reaches it only when subscribed` |
| T2 | R6.3, R3.5, R5.4 | `Scenario: A Slack reply with the gate grant is recorded unmarked and the gate classifies it on ingress` |
| T2 | R3.5, A5 | `Scenario: A Slack control keyword with the grant is executed by ingress, not the pipeline` |
| T2 | R2.2, R2.3 | `Scenario: Without a grant a reply is session input and nothing more` |
| T2 | R6.5, R3.6 | `Scenario: A top-level DM becomes a labelled issue bound to its thread` |
| T2 | R6.4, R4.4 | `Scenario: The complete node announces work-item-complete with a link` |
| T2 | R4.3 | `Scenario: An Approve button press enters the pipeline as that member's reply` |
| T8 | A1–A10 | one negative test each, named in `design.md` § Security design |
| T10 | R7.1, R7.2, R7.3 | refusal, migration, idempotence, parity |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. The Slack SDK client and `gh` are faked at the process
  boundary; `tmux` is not needed (delivery is monkeypatched).
- **Fixtures & data:** in-test dicts; a temp `state.root` per test.
- **Credentials:** none. `THE_LOOP_SLACK_BOT_TOKEN` is set to a dummy value inside tests
  that need the channel enabled — by name, never a real token.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T10, T12 | command, counts, duration, raw tail of the output | `verification.md` |
| T13 | the abuse-case table with verdicts and the tests that close each | `security-review.md` |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_identity.py cli/tests/test_bus.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py cli/tests/test_bus_integration.py`
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests -k "abuse or unauthorized or envelope or grant or kickoff"`
- [x] T10 — `uv run --project cli python -m pytest -q cli/tests/test_migrations.py cli/tests/test_config_schema_parity.py cli/tests/test_configschema.py`
- [x] T12 — `make check`
- [x] T13 — `evidence/security-review.md`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `pytest cli/tests/test_channels.py cli/tests/test_identity.py cli/tests/test_bus.py` | pass | [`evidence/verification.md`](evidence/verification.md) § T1 |
| T2 | `pytest cli/tests/test_channels_integration.py cli/tests/test_bus_integration.py` | pass | § T2 |
| T8 | `pytest cli/tests -k "abuse or unauthorized or envelope or grant or kickoff"` | pass | § T8 |
| T10 | `pytest cli/tests/test_migrations.py cli/tests/test_config_schema_parity.py cli/tests/test_configschema.py` | pass | § T10 |
| T12 | `make check` | pass — 2844 passed, 1 skipped; ruff, format, pyright, validator and markdownlint clean | § T12 |
| T13 | checklist against A1–A10 | pass — ten closed; human sign-off outstanding | [`evidence/security-review.md`](evidence/security-review.md) |

**Not executed:** none.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
