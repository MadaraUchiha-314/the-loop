---
type: testing-plan
phase: test-planning
workItem: "issue-312"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: the thread is the work item's

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `ChannelState`: the `conversations` map, `bind` writing both maps, `thread_for` preferring it, legacy backfill, eviction with the cap, the lock; `SlackBotChannel.post`: root shape, event as first reply, reuse, failure without a second root, permalink best-effort; `channels threads` and `status` output | `uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_eventlog.py` |
| T2 | Integration (scenario) | yes | the five Gherkin scenarios below through the real modules with the SDK client and `gh` faked | `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py cli/tests/test_bus_integration.py cli/tests/test_standing_channels_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API route changes | | |
| T4 | End-to-end | n/a — needs a Slack workspace; the integration rows fake exactly the SDK client | | |
| T5 | UI / visual | n/a — the root's Block Kit is asserted structurally (T1) | | |
| T6 | Snapshot | n/a — field-by-field assertions on one root shape are stricter and survive a reorder | | |
| T7 | Performance / load | n/a — one root post and one permalink call per work item; the lock covers a single request | | |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A5 (`design.md` § Security design) | `uv run --project cli python -m pytest -q cli/tests -k "root_shaped or ref_alone or failed_permalink or corrupt_state or without_flock"` |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | yes | a `slack.json` written before this work item (`threads` + `cursors` only) loads, answers `thread_for`, and is rewritten with `conversations` on the next save; no config migration (no config key changes) | `uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_channels_integration.py -k pre_issue_312` |
| T11 | Manual exploratory | n/a — the reviewer's walk-through is the PR briefing's "what to check" | | |
| T12 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T13 | Security review (gate) | yes | the-loop checklist against A1–A5, recorded as evidence; tier 3 needs no human sign-off (`humanSignOffMinTier: 4`) | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R3.1, R3.4, R3.5 | `bind` writes both maps; `thread_for` reads the conversation; a threads-only file backfills; eviction drops the conversation; no token in the file |
| T1 | R1.4 | two `locked()` sections on one path serialize (a second thread waits) |
| T1 | R1.1, R1.2, R1.3, R2.2 | the first post is a root + a reply; the second is one reply; the root names the ref and carries the link button; the reply carries the event's blocks |
| T1 | R2.3 | a failing reply raises `ChannelError` and posts no root |
| T1 | R3.2, R3.3 | `channel.thread_opened` is emitted with ids only; `channels threads` lists and filters; `status` counts work items |
| T2 | R1.1–R1.3, R2.1 | `Scenario: Every message about a work item is a reply in its one thread` |
| T2 | R1.4 | `Scenario: Two writers open one thread` |
| T2 | R1.5, R3.1 | `Scenario: A kickoff thread is the work item's conversation` |
| T2 | R3.4 | `Scenario: A pre-issue-312 state file keeps its threads` |
| T2 | R3.3 | `Scenario: channels threads lists the conversation` |
| T2 | R1.6 | the standing-session scenarios (issue-277), re-pointed: the announcement is the first reply |
| T8 | A1–A5 | one negative test each, named in `design.md` § Security design |
| T10 | R3.4 | the legacy-file cases above |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. The Slack SDK client is faked at the process boundary;
  `gh` is faked where a scenario records on the ledger; `tmux` is not needed.
- **Fixtures & data:** in-test dicts; a temp `state.root` per test; a hand-written
  pre-issue-312 `slack.json`.
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

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_eventlog.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py cli/tests/test_bus_integration.py cli/tests/test_standing_channels_integration.py`
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests -k "root_shaped or ref_alone or failed_permalink or corrupt_state or without_flock"`
- [x] T10 — `uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_channels_integration.py -k pre_issue_312`
- [x] T12 — `make check`
- [x] T13 — `evidence/security-review.md`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_eventlog.py` | pass — 70 passed | [`evidence/verification.md`](evidence/verification.md) |
| T2 | `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py cli/tests/test_bus_integration.py cli/tests/test_standing_channels_integration.py` | pass — 29 passed (the five scenarios among them) | [`evidence/verification.md`](evidence/verification.md) |
| T8 | `uv run --project cli python -m pytest -q cli/tests -k "root_shaped or ref_alone or failed_permalink or corrupt_state or without_flock"` | pass — 5 passed (A1–A5) | [`evidence/verification.md`](evidence/verification.md) |
| T10 | `uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_channels_integration.py -k pre_issue_312` | pass — 2 passed | [`evidence/verification.md`](evidence/verification.md) |
| T12 | `make check` | pass — lint, format, typecheck, config validation, 2950 passed / 1 skipped | [`evidence/verification.md`](evidence/verification.md) |
| T13 | the-loop checklist over A1–A5 | pass; no human sign-off at tier 3 | [`evidence/security-review.md`](evidence/security-review.md) |

**Not executed:** none.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
