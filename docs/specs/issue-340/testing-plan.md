---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#340"
status: in-review
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: `the-loop progress`

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md). The
> results are in [`evidence/verification.md`](evidence/verification.md).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (core) | yes | shortening (two lines, collapsed, truncated); config defaults and malformed values; the five statuses; the per-item interval; the interval ending; a zero interval; an empty or malformed input refused before any read | `cli/tests/test_progress.py` |
| T2 | Unit (label read) | yes | the GitHub label comes from the issue; the Jira comparison uses the Jira-safe form | same |
| T3 | Route and CLI | yes | `POST /sessions/progress` reaches the core with the caller's actor and answers 400 on an empty report; the CLI posts through a running service | same |
| T4 | Unit (room policy) | yes | `session.progress` posts once, then edits its own line, never a phase's | `cli/tests/test_room_policy.py` |
| T5 | Integration (Gherkin) | yes | a real `SlackBotChannel` posts one message, edits it for the next report, and defuses `<!channel>` and `<@U…>` in the message and its plain-text fallback | `cli/tests/test_channels_declared_integration.py` |
| T6 | Contract and docs | yes | the served OpenAPI surface equals the contract (worker and manager); the command page, the config page and the event catalog are pinned to the code | `test_api_contract_parity.py`, `test_docs_parity.py`, `test_configschema.py` |
| T7 | Regression (full suite + hooks) | yes | ruff, ruff format, pyright, all CLI tests, markdownlint | `make check` equivalents |
| T8 | Security | yes (review) | untrusted text, flood brakes, fail-closed on an unreadable label | `evidence/security-review.md` |
| T9 | Live Slack | n/a here | needs a workspace and a bot token; the fake client pins the calls made | |
| T10 | UI / migration / performance | n/a | no UI, no stored data; one label read and one log scan per call | |

## Requirement trace

| Requirement | Tests |
|-------------|-------|
| R1.1, R1.3, R1.4 | T1 |
| R1.2, R1.5 | T3 |
| R2.1–R2.6 | T1, T2 |
| R3.1–R3.3 | T1 |
| R4.1, R4.2 | T6 |
| R4.3 | T4, T5 |
| R4.4 | T5 |
| R5.1 | T6 |
| R5.2 | review of the doc diff |
| Security considerations | T1, T5, T8 |

## Verification environment

This repository's own checkout, Python 3.12. The tracker is a monkeypatched label read; the
bus is a recorded double; Slack is `FakeSlackClient`; the event log is a real file in a
temporary directory, so the rate limit reads what the verb wrote.
