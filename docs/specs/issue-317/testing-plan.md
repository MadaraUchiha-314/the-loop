---
type: testing-plan
phase: test-planning
workItem: "issue-317"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: the start opens the conversation

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `SlackBotChannel.open`: root with origin `start`, no reply, idempotent, `ChannelError` on no channel/token/ts; `bus.open_conversation`: every opening channel, the ledger skipped, a failure a result + `channel.open_failed`; `conversation_opener`: config per call, no section → nothing; `Dispatcher`: opener called once on spawn with the ref, before the checkout, never on a refusal, a raising opener contained | `uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_bus.py cli/tests/test_control_integration.py cli/tests/test_eventlog.py` |
| T2 | Integration (scenario) | yes | the four Gherkin scenarios below through the real dispatcher + bus + Slack channel with the SDK client and tmux faked | `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py cli/tests/test_control_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API route changes; the start route's body and result are unchanged | | |
| T4 | End-to-end | n/a — needs a Slack workspace and tmux; the scenario rows fake exactly the SDK client and the runner | | |
| T5 | UI / visual | n/a — the root's Block Kit is issue-312's, asserted there | | |
| T6 | Snapshot | n/a — field assertions on one record shape | | |
| T7 | Performance / load | n/a — one root post per work item, moved earlier rather than added; bounded by the SDK timeout on the work item's own worker | | |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A5 (`design.md` § Security design) | `uv run --project cli python -m pytest -q cli/tests -k "unauthorized_start_opens or refused_start_opens or outage_never_fails_the_spawn or handed_the_ref_alone or still_opens_on_start"` |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | yes | a `slack.json` carrying `origin: start` read by the `_record` coercion path; a pre-issue-312 file still backfills (issue-312 T10 re-run); no config key changes, so no config migration | `uv run --project cli python -m pytest -q cli/tests/test_channels.py -k "pre_issue_312 or origin"` |
| T11 | Manual exploratory | n/a — the reviewer's walk-through is the PR briefing's "what to check" | | |
| T12 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T13 | Security review (gate) | yes | the-loop checklist against A1–A5, recorded as evidence; tier 3 needs no human sign-off (`humanSignOffMinTier: 4`) | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.2, R2.1, R2.2 | `open` posts one root, binds with origin `start`, emits `channel.thread_opened` with ids only |
| T1 | R1.3 | a second `open`, and an `open` after a `post`, post nothing |
| T1 | R1.5, R2.2 | no channel id / no token / no ts → `ChannelError`; the bus turns it into a result and `channel.open_failed` |
| T1 | R1.6 | `open_conversation` skips the ledger and any channel without `open` |
| T1 | R3.1, R3.2, R3.3 | the opener reads config per call and does nothing without a `channels` section; `_build_dispatcher` wires it; a dispatcher without one opens nothing |
| T1 | R1.1, R1.4 | the dispatcher calls the opener once, with the ref, before the workspace; not on a refused start; a raising opener is contained |
| T2 | R1.1, R1.2, R1.7, R2.1 | `Scenario: A start opens the work item's thread before any event` |
| T2 | R1.4 | `Scenario: A refused start opens no thread` |
| T2 | R1.3 | `Scenario: A restarted work item keeps its thread` |
| T2 | R1.5 | `Scenario: A Slack outage never fails the spawn` |
| T8 | A1–A5 | one negative test each, named in `design.md` § Security design |
| T10 | R2.1 | the origin coercion and the legacy backfill |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. The Slack SDK client is faked at the process boundary;
  tmux is the test suite's `FakeTmux`; `gh` is faked where the announcer would post.
- **Fixtures & data:** in-test dicts; a temp `state.root` per test.
- **Credentials:** none. `THE_LOOP_SLACK_BOT_TOKEN` is set to a dummy value inside tests
  that need the channel enabled — by name, never a real token.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T10, T12 | command, counts, duration, raw tail of the output; red → green per task | `verification.md` |
| T13 | the abuse-case table with verdicts and the tests that close each | `security-review.md` |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_bus.py cli/tests/test_control_integration.py cli/tests/test_eventlog.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py cli/tests/test_control_integration.py`
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests -k "unauthorized_start_opens or refused_start_opens or outage_never_fails_the_spawn or handed_the_ref_alone or still_opens_on_start"`
- [x] T10 — `uv run --project cli python -m pytest -q cli/tests/test_channels.py -k "pre_issue_312 or origin"`
- [x] T12 — `make check`
- [x] T13 — `evidence/security-review.md`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_bus.py cli/tests/test_control_integration.py cli/tests/test_eventlog.py` | pass — 153 passed | [`evidence/verification.md`](evidence/verification.md) |
| T2 | `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py cli/tests/test_control_integration.py` | pass — 54 passed (the four scenarios among them) | [`evidence/verification.md`](evidence/verification.md) |
| T8 | `uv run --project cli python -m pytest -q cli/tests -k "unauthorized_start_opens or refused_start_opens or outage_never_fails_the_spawn or handed_the_ref_alone or still_opens_on_start"` | pass — 6 passed (A1–A5; A2 twice, unit and scenario) | [`evidence/verification.md`](evidence/verification.md) |
| T10 | `uv run --project cli python -m pytest -q cli/tests/test_channels.py -k "pre_issue_312 or origin"` | pass — 3 passed | [`evidence/verification.md`](evidence/verification.md) |
| T12 | `make check` | pass — lint, format, typecheck, config validation, full suite | [`evidence/verification.md`](evidence/verification.md) |
| T13 | the-loop checklist over A1–A5 | pass; no human sign-off at tier 3 | [`evidence/security-review.md`](evidence/security-review.md) |

**Not executed:** none.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
