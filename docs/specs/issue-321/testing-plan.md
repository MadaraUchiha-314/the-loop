---
type: testing-plan
phase: test-planning
workItem: "issue-321"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: a channel's gate answer reaches the gate

> Derived from `bugfix.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the reader equals the dispatcher's coupling (control config, control-store root, allow-list, registry dir); coupling off → `False`; no record → `None`; the read mutates no graph state; each row of the classification table through `process_reply` with the read patched to `True` / `False` / `None`, with and without the grant; the keyword still outranks; the deferred record is unmarked, enveloped `gate.feedback`, attributed as a *reply*; `channel.reply_received` carries `gate` | `uv run --project cli python -m pytest -q cli/tests/test_channels.py` |
| T2 | Integration (scenario) | yes | the issue's reproduction, real state end to end: a checkout with `origin`, a registry record with that `cwd`, `graph-state.json` parked at `requirements-approval`, a recorded `start`, the default control policy; an authorized Slack reply through `poll_once` → an unmarked `gate.feedback` record the ledger's ingress attributes to the person; and the no-session-record scenario → the same record, attributed as a reply | `uv run --project cli python -m pytest -q cli/tests/test_bus_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API route changes | | |
| T4 | End-to-end | n/a — the ledger's ingress and the gate hooks are exercised by their own suites (`test_graphlink_integration.py`, `test_routing.py`); T2 hands them the record shape they already accept | | |
| T5 | UI / visual | n/a — no UI | | |
| T6 | Snapshot | n/a — assertions on a record body and an event field | | |
| T7 | Performance / load | n/a — one registry read and one state read per reply, as before | | |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A5 (`bugfix.md` § Security considerations) | `uv run --project cli python -m pytest -q cli/tests/test_channels.py -k "without_the_grant_is_a_marked_reply or unlisted_member_is_dropped_before or keyword_outranks_an_unreadable or defers_to_the_ledger or read_moves_nothing"` |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | yes | no config change; a 13.3.0 config with `publish: [work-item.reply]` behaves exactly as before (T1's no-grant rows); the event catalog's description still pins docs and CLI together | `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py` |
| T11 | Manual exploratory | n/a — the reviewer's walk-through is the PR briefing's "what to check" | | |
| T12 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T13 | Security review (gate) | yes | the-loop checklist against A1–A5, recorded as evidence; tier 3 needs no human sign-off (`humanSignOffMinTier: 4`) | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.2 | `test_the_pipeline_reads_the_graph_through_the_dispatchers_own_coupling` |
| T1 | R1.3, R2.2, A4 | `test_an_unreadable_gate_defers_to_the_ledger_when_the_channel_may_answer_gates` |
| T1 | R1.4, A1 | `test_an_unreadable_gate_without_the_grant_is_a_marked_reply_as_before` |
| T1 | R1.5 | `test_a_disabled_graph_coupling_means_no_gate_to_answer` |
| T1 | R1.6 | `test_a_graph_that_says_not_at_a_gate_keeps_the_reply_direct` |
| T1 | R1.7, A3 | `test_a_control_keyword_outranks_an_unreadable_gate` |
| T1 | A2 | `test_an_unlisted_member_is_dropped_before_the_gate_is_even_read` |
| T1 | A5 | `test_the_pipelines_read_moves_nothing` |
| T1 | R1.3 | `test_no_session_record_is_an_unknown_gate_not_a_closed_one` |
| T1 | R2.1 | `test_the_reply_event_says_what_the_gate_read_returned` |
| T2 | R1.1, R1.8 | `Scenario: An approval from Slack reaches the gate under the daemon's default control policy` |
| T2 | R1.3 | `Scenario: A reply for a work item with no session record is left to the ledger` |
| T10 | R3.1 | docs parity, schema parity |

## Verification environment

- **Repositories:** this repo only. T2 runs `git init` and `git remote add` in a temp
  directory (the coupling's ownership check reads the checkout's `origin`).
- **Services / containers:** none. The Slack SDK client, the ledger writer and session
  delivery are faked at their injection points.
- **Fixtures & data:** temp directories per test; graph state written by `GraphState`.
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
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_bus_integration.py`
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests/test_channels.py -k "without_the_grant_is_a_marked_reply or unlisted_member_is_dropped_before or keyword_outranks_an_unreadable or defers_to_the_ledger or read_moves_nothing"`
- [x] T10 — `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py`
- [x] T12 — `make check`
- [x] T13 — `evidence/security-review.md`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_channels.py` | pass — 73 passed (11 new) | [`evidence/verification.md`](evidence/verification.md) |
| T2 | `uv run --project cli python -m pytest -q cli/tests/test_bus_integration.py` | pass — 10 passed (the two scenarios, red first) | [`evidence/verification.md`](evidence/verification.md) |
| T8 | `uv run --project cli python -m pytest -q cli/tests/test_channels.py -k "…"` | pass — 5 passed (A1–A5) | [`evidence/verification.md`](evidence/verification.md) |
| T10 | `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py` | pass — 8 passed | [`evidence/verification.md`](evidence/verification.md) |
| T12 | `make check` | pass — lint (ruff, markdownlint over 965 files), format, pyright, config validation, full suite: 3033 passed, 1 skipped | [`evidence/verification.md`](evidence/verification.md) |
| T13 | the-loop checklist over A1–A5 | pass; no human sign-off at tier 3 | [`evidence/security-review.md`](evidence/security-review.md) |

**Not executed:** none.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
