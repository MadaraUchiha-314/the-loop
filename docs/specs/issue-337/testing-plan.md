---
type: testing-plan
phase: test-planning
workItem: "issue-337"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: Execute / Start buttons, the outcome on the message, the status steps

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `SlackChannelConfig.command_buttons` / `keyword` / `command_buttons_for` (socket + grant, a renamed keyword, a disabled keyword, poll mode); `expected_commands` (the marker on `comment.agent` only); `render_blocks` with `commands` (value = keyword, `action_id` under the prefix, nothing without socket + grant); `render_reply_blocks`; `report_press` (blocks rebuilt, link buttons kept, command buttons removed on success / kept on failure, the words, no value or token in the text, a refused update is `channel.press_report_failed` and `False`, no token is quiet); `process_reply` carries `url`; `_button_lines` per configuration; `PHASE_SELECTION_MARKER == selection.SELECTION_MARKER`; the two event types in `EVENT_TYPES` | `uv run --project cli python -m pytest -q cli/tests/test_channels.py -k "button or press or command_buttons or expected_commands or reply_blocks"` |
| T2 | Integration (scenario) | yes | through the socket handlers: an Execute press records the same unmarked comment a typed `the-loop execute` records and the ingress's parser reads `execute`, then the message is edited (buttons gone, ✅ line, link); a kickoff reply carries Start and its press records `the-loop start`; an unlisted member's press edits nothing; a refused record keeps the button and says why | `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py -k "press or button"` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API route changes | | |
| T4 | End-to-end | n/a — the ledger's ingress executing a relayed keyword is `test_routing.py` / `test_poller.py`'s subject; T2 proves the record is the one this work item writes | | |
| T5 | UI / visual | n/a — Slack renders Block Kit; the block structure is asserted in T1/T2 | | |
| T6 | Snapshot | n/a — assertions on block dictionaries and call arguments | | |
| T7 | Performance / load | n/a — one press is one record and one `chat.update` | | |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A7 (`requirements.md` § Security considerations) | `uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_channels_integration.py -k "unauthorized or unlisted or crafted or grant or press_report or poll_mode or twice or cant_update"` |
| T9 | Accessibility | n/a — no UI of the-loop's own | | |
| T10 | Migration / upgrade | yes | a 13.9.0 config parses unchanged (no new key); both schema copies untouched and identical; docs parity; the event catalog knows the two types; the existing button and reaction suites green | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py cli/tests/test_channels.py cli/tests/test_channels_integration.py cli/tests/test_bus.py` |
| T11 | Manual exploratory | n/a — no Slack workspace is reachable from this session; the reviewer's walk-through is the PR briefing's "what to check" | | |
| T12 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T13 | Security review (gate) | yes | the-loop checklist against A1–A7, recorded as evidence; tier 3 needs no human sign-off | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.4, R1.5 | `test_the_checklist_mirror_earns_an_execute_button_with_the_keyword_as_value`, `test_expected_commands_reads_the_marker_on_agent_comments_only`, `test_no_command_button_without_socket_and_the_grant`, `test_a_disabled_keyword_renders_no_button`, `test_a_renamed_keyword_is_the_buttons_value` |
| T1 | R1.2 | `test_reply_blocks_carry_the_start_button` |
| T1 | R2.1, R2.2, R2.6 | `test_report_press_rewrites_the_message_with_the_outcome`, `test_a_failed_press_keeps_the_buttons_and_says_why`, `test_the_press_report_never_echoes_the_value_or_a_token` |
| T1 | R2.3 | `test_a_refused_update_is_an_event_and_false`, `test_report_press_without_a_token_is_quiet` |
| T1 | R2.4 | `test_an_approve_press_is_reported_too` |
| T1 | R3.1, R3.2 | `test_status_names_both_button_sets_and_the_missing_steps`, `test_status_prints_no_steps_when_buttons_are_on`, `test_status_prints_only_the_steps_that_apply` |
| T1 | R4.1 | `test_the_marker_is_the_selection_hooks`, `test_eventlog.py::test_every_emitted_event_type_is_documented` |
| T2 | R1.3, R2.1, R2.5 | `Scenario: An Execute press records what a typed the-loop execute records, and the message says so` |
| T2 | R1.2, R1.3 | `Scenario: A kickoff reply carries Start and its press records the start keyword` |
| T2 | A1, R2.3 | `Scenario: An unlisted member's press edits nothing` |
| T2 | R2.2, R2.3 | `Scenario: A press whose record the ledger refused keeps its button and says why` |
| T8 | A1–A7 | the selection above, one named test each (see `evidence/security-review.md`) |
| T10 | R4.1 | docs parity, schema parity, the event catalog, the existing suites |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. The Slack SDK is faked at its injection point
  (`client_factory`, with `chat_update` added to the fake); the ledger writer
  (`post_comment`) and the delivery (`reply_session`) are faked as the existing suites
  fake them; no tmux, no `gh`.
- **Fixtures & data:** temp directories per test; the fake client records posts,
  reactions and updates.
- **Credentials:** none. `THE_LOOP_SLACK_BOT_TOKEN` is set to a dummy value by name
  where a channel is built.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T10, T12 | command, counts, duration, raw tail of the output; red → green per task | `verification.md` |
| T13 | the abuse-case table with verdicts and the tests that close each | `security-review.md` |

## Verification activities

- [ ] T1 — the unit selection above
- [ ] T2 — the scenario selection above
- [ ] T8 — the abuse-case selection above
- [ ] T10 — the parity, catalog and existing-suite selection above
- [ ] T12 — `make check`
- [ ] T13 — `evidence/security-review.md`

## Verification results

> Filled at `verification`.

| Row | Command | Outcome | Evidence |
|-----|---------|---------|----------|
| | | | |

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
