---
type: testing-plan
phase: test-planning
workItem: "issue-334"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: drive the loop from Slack — the keywords in the thread, a slash command for the rest

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `parse_invocation` over every vocabulary row and every refusal (unknown verb, extra tokens, two keywords, two addresses, a collaborator command without a login, a disabled keyword, an operator-renamed keyword); `resolve_work_item` over the four shapes and the resolved-host rule; `may_target` over `kickoff.repo`, a poll repo, a managed work item, a bound conversation, a foreign repo and a failing read; `handle_slash_command` per family with fakes (the ledger writer, `lifecycle`, `standing`, `respond`): the composed line, the unmarked enveloped record, the facade calls and their rendering, every drop, the duplicate ring, the answer discipline; the catalog rows; the event types | `uv run --project cli python -m pytest -q cli/tests/test_channels_commands.py` |
| T2 | Integration (scenario) | yes | through the listener's handler: `/the-loop start #7` records the same comment a thread keyword records and the ingress's parser reads it as `start`; `/the-loop status` and `/the-loop standing start` reach the facade and answer ephemerally; an unlisted member's command leaves nothing; a thread keyword with the grant relays unmarked (R1, pinned) | `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API route changes; the facade is called, not exposed anew | | |
| T4 | End-to-end | n/a — the ledger's ingress executing a relayed keyword is `test_routing.py` / `test_poller.py`'s subject already; T2 proves the record they read is the one this work item writes | | |
| T5 | UI / visual | n/a — Slack's own slash-command UI and plain ephemeral text | | |
| T6 | Snapshot | n/a — assertions on call arguments, record bodies and rendered lines | | |
| T7 | Performance / load | n/a — one command is one ledger write or one facade call, acknowledged before handling | | |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A9 (`requirements.md` § Security considerations) | `uv run --project cli python -m pytest -q cli/tests/test_channels_commands.py -k "abuse or unauthorized or grant or foreign or duplicate or response_url or grammar or payload"` |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | yes | a 13.8.0 config parses unchanged (no new key; the two grants are opt-in); both schema copies identical; docs parity; the event catalog knows the new types; the manifest pinned to the guide; the `publish` table pinned to the catalog | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py cli/tests/test_channels.py` |
| T11 | Manual exploratory | n/a — no Slack workspace is reachable from this session; the reviewer's walk-through is the PR briefing's "what to check" and the guide's setup section | | |
| T12 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T13 | Security review (gate) | yes | the-loop checklist against A1–A9, recorded as evidence; tier 3 needs no human sign-off (`humanSignOffMinTier: 4`) | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R2.2 | `test_parse_help`, `test_parse_instance_verbs`, `test_parse_standing_verbs`, `test_parse_work_item_verbs_from_the_configured_keywords`, `test_parse_refuses_*` |
| T1 | R2.3 | `test_resolve_work_item_shapes`, `test_resolve_bare_numbers_need_kickoff_repo`, `test_resolve_applies_the_resolved_host` |
| T1 | R2.4, A3 | `test_may_target_*`, `test_a_failing_read_contributes_nothing` |
| T1 | R2.5, A6 | `test_parse_refuses_a_malformed_standing_name`, `test_parse_refuses_a_malformed_address`, `test_parse_refuses_a_malformed_login` |
| T1 | R3.1, A1 | `test_an_unlisted_member_is_dropped_before_parsing`, `test_an_empty_allowlist_denies_everyone` |
| T1 | R3.2, A2 | `test_a_verb_without_its_grant_is_refused_and_named` |
| T1 | R3.3, A4 | `test_a_work_item_verb_records_the_composed_line_unmarked`, `test_the_recorded_line_is_built_from_the_keyword_not_the_text` |
| T1 | R3.4, A8 | `test_command_events_carry_ids_never_text` |
| T1 | R3.5 | `test_status_renders_the_facade_document`, `test_restart_and_upgrade_schedule_through_the_facade`, `test_standing_verbs_call_the_facade` |
| T1 | R3.6 | `test_a_failing_ledger_is_a_recorded_outcome`, `test_a_raising_facade_is_answered_not_raised`, `test_a_failed_answer_keeps_the_outcome` |
| T1 | A5 | `test_an_off_host_response_url_is_never_posted_to` |
| T1 | A7 | `test_restart_passes_one_boolean_and_the_config_path` |
| T1 | A9 | `test_a_duplicate_trigger_is_dropped` |
| T1 | R4.1 | `test_the_manifest_is_packaged_and_printed` |
| T2 | R1.1, R1.2, R3.3 | `Scenario: A slash command start records what a thread keyword records` |
| T2 | R2.1, R3.5 | `Scenario: A slash command status answers from the facade`, `Scenario: A slash command starts a standing session` |
| T2 | R3.1 | `Scenario: An unlisted member's slash command leaves nothing` |
| T2 | R1.1 | `Scenario: A control keyword in a bound thread relays unmarked for the ingress` |
| T10 | R4.1, R4.3 | `test_the_guide_reproduces_the_packaged_manifest`, `test_the_docs_list_every_publishable_event`, docs parity, schema parity, event catalog |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. The Slack SDK is faked at its injection points
  (`respond`, `client_factory`); the ledger writer (`post_comment`) and the core facade
  (`lifecycle`, `standing`) are faked as the existing suites fake them; no tmux, no `gh`.
- **Fixtures & data:** temp directories per test; the fake facade records its calls.
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

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_channels_commands.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py`
- [x] T8 — the abuse-case selection above
- [x] T10 — `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py cli/tests/test_channels.py`
- [x] T12 — `make check`
- [x] T13 — `evidence/security-review.md`

## Verification results

> Filled at `verification` (2026-09-09, head of `claude/github-issue-334-k9yw0i`).

| Row | Command | Outcome | Evidence |
|-----|---------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_channels_commands.py` | pass — 47 passed | [`evidence/verification.md`](evidence/verification.md) |
| T2 | `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py` | pass — 24 passed (4 new scenarios) | [`evidence/verification.md`](evidence/verification.md) |
| T8 | the abuse-case selection (`-k "abuse or unauthorized or grant or …"`) | pass — 15 passed, A1–A9 each closed by a named test | [`evidence/verification.md`](evidence/verification.md), [`evidence/security-review.md`](evidence/security-review.md) |
| T10 | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py cli/tests/test_channels.py cli/tests/test_bus.py` | pass — 162 passed; both schema copies byte-identical; the manifest pinned to the guide; the `publish` table pinned to the catalog | [`evidence/verification.md`](evidence/verification.md) |
| T12 | `make check` | pass — ruff, ruff format, markdownlint (1024 files), pyright, `validate_config`, the full suite | [`evidence/verification.md`](evidence/verification.md) |
| T13 | the-loop checklist | pass — nine abuse cases, nine closed; no human sign-off at tier 3 | [`evidence/security-review.md`](evidence/security-review.md) |

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
