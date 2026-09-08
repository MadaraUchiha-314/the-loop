---
type: testing-plan
phase: test-planning
workItem: "issue-325"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: the Slack channel acknowledges an accepted reply with a reaction

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the config block (defaults equal the schema, `enabled: false`, `""`, colon stripping, a malformed name refused per state, a non-mapping block); `react` against a fake client (the call's arguments, disabled/skipped states, no token, a raising client → `False` + `channel.reaction_failed`); each pipeline path with a fake-client channel: an accepted reply → `received` then `completed`; undeliverable → `error`; a failed mirror → `error`; a relayed `gate.feedback` / `control.command` → `completed` on the record alone; a standing session's reply → `completed` on delivery; a kickoff → `received` then `completed`, `error` on create-failed; every drop → no reaction; a raising client changes no outcome; event payloads carry no text or token | `uv run --project cli python -m pytest -q cli/tests/test_channels.py` |
| T2 | Integration (scenario) | yes | end to end through `poll_once` with a bound thread: 👀 then ✅ on the reply's own `ts`; through `handle_socket_event` and a button press through `handle_socket_action` (the reaction on the pressed message); a Slack that refuses `reactions.add` never fails the delivery | `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API route changes | | |
| T4 | End-to-end | n/a — the ledger's ingress and the session delivery are exercised by their own suites; T2 hands them the same calls as before | | |
| T5 | UI / visual | n/a — no UI; the visible change is three emoji on a Slack message | | |
| T6 | Snapshot | n/a — assertions on call arguments and event fields | | |
| T7 | Performance / load | n/a — one or two SDK calls per accepted message, bounded by the SDK timeout, in the thread that already makes the ledger write | | |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A6 (`requirements.md` § Security considerations) | `uv run --project cli python -m pytest -q cli/tests/test_channels.py -k "reaction"` |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | yes | a config without the block parses to the defaults (T1's default rows); both schema copies identical; every new schema leaf documented with type and default; the event catalog knows both new types | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py` |
| T11 | Manual exploratory | n/a — no Slack workspace is reachable from this session; the reviewer's walk-through is the PR briefing's "what to check" | | |
| T12 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T13 | Security review (gate) | yes | the-loop checklist against A1–A6, recorded as evidence; tier 3 needs no human sign-off (`humanSignOffMinTier: 4`) | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R2.1, R2.4, R2.5 | `test_reaction_config_defaults_match_the_schema`, `test_a_config_without_the_block_reacts_with_the_defaults` |
| T1 | R2.2, R2.3, A4 | `test_reactions_can_be_disabled_or_skipped_per_state`, `test_a_malformed_reaction_name_is_refused_and_the_state_skipped`, `test_colons_around_a_reaction_name_are_stripped` |
| T1 | R1.5, R1.6, R3.3 | `test_react_adds_the_named_reaction_on_the_message` |
| T1 | R3.1, R3.2, A3, A5 | `test_react_never_raises_and_records_the_failure`, `test_react_without_a_token_is_a_quiet_noop` |
| T1 | R1.1, R1.2 | `test_an_accepted_reply_is_acknowledged_received_then_completed` |
| T1 | R1.3 | `test_an_undeliverable_reply_is_acknowledged_with_error`, `test_a_failed_mirror_is_acknowledged_with_error` |
| T1 | R1.2 | `test_a_relayed_gate_answer_completes_on_its_record`, `test_a_standing_sessions_reply_completes_on_delivery` |
| T1 | R1.1–R1.3 (kickoff) | `test_a_kickoff_is_acknowledged_received_then_completed`, `test_a_failed_kickoff_is_acknowledged_with_error` |
| T1 | R1.4, A1, A2 | `test_a_dropped_message_gets_no_reaction` (bot, empty allow-list, unlisted member, unpublishable, unmapped) |
| T1 | R3.1, A3 | `test_a_refused_reaction_changes_no_outcome` |
| T1 | R3.4, A6 | `test_reaction_events_carry_no_text_or_token` |
| T2 | R1.1, R1.2, R1.5 | `Scenario: An accepted Slack reply is acknowledged on the reply itself` |
| T2 | R1.5 (button) | `Scenario: A button press is acknowledged on the message carrying the button` |
| T2 | R3.1, A3 | `Scenario: A Slack that refuses the reaction never fails the delivery` |
| T10 | R2.4, R4.1, R4.2 | schema parity, docs parity (P4, P5), event catalog |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. The Slack SDK client is faked at its injection point
  (`client_factory`, or `the_loop.channels.slack.build_client` monkeypatched); the ledger
  writer and session delivery are faked as the existing suites fake them.
- **Fixtures & data:** temp directories per test; the fake client records
  `reactions_add` calls as it records posts.
- **Credentials:** none. `THE_LOOP_SLACK_BOT_TOKEN` is set to a dummy value by name.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T10, T12 | command, counts, duration, raw tail of the output; red → green per task | `verification.md` |
| T13 | the abuse-case table with verdicts and the tests that close each | `security-review.md` |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_channels.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py`
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests/test_channels.py -k "reaction"`
- [x] T10 — `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py`
- [x] T12 — `make check`
- [x] T13 — `evidence/security-review.md`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_channels.py` | pass — 100 passed (27 new) | [`evidence/verification.md`](evidence/verification.md) |
| T2 | `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py` | pass — 20 passed (3 new scenarios, red first) | [`evidence/verification.md`](evidence/verification.md) |
| T8 | `uv run --project cli python -m pytest -q cli/tests/test_channels.py -k reaction` | pass — 15 passed (A1–A6) | [`evidence/verification.md`](evidence/verification.md) |
| T10 | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py` | pass — 22 passed | [`evidence/verification.md`](evidence/verification.md) |
| T12 | `make check` | pass — lint (ruff, markdownlint over 985 files), format, pyright, config validation, full suite: 3138 passed, 1 skipped | [`evidence/verification.md`](evidence/verification.md) |
| T13 | the-loop checklist over A1–A6 | pass; no human sign-off at tier 3 | [`evidence/security-review.md`](evidence/security-review.md) |

**Not executed:** none.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
