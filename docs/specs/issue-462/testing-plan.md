---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#462"
status: in-review
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: monitor a pull request's CI and heal its failing checks

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md). The
> results are in [`evidence/verification.md`](evidence/verification.md).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (client) | yes | `job_log_tail` reads `Location` from the API's `302` without following it, fetches the signed URL with no `Authorization`, strips timestamps and ANSI codes, keeps the last *n* lines, marks a log cut at the read cap, refuses a non-`https` redirect, and refuses a bad job id before any request | `cli/tests/test_ghapi.py -k job_log` |
| T2 | Unit (core) | yes | `pull_request_checks` lists check runs and statuses with `failing` matching the rollup; `--failing` filters; failing Actions runs get `logTail`, others do not; at most five logs; a log failure is `logError` with exit 0; `log_lines=0` fetches none; a refused read is exit 1; `startup_failure` counts as failing | `cli/tests/test_github_ops.py -k checks` |
| T3 | Unit (abuse) | yes | untrusted host and bare number without `--work-item` are refused before any request | same |
| T4 | CLI | yes | `the-loop pr checks 12 --work-item … --failing` prints JSON and exits 0 in-process | `cli/tests/test_github_verbs_cli.py -k checks` |
| T5 | Integration (Gherkin) | yes | the route through the real service app returns the checks with a log tail | `cli/tests/test_github_verbs_integration.py -k checks` |
| T6 | Contract | yes | served OpenAPI equals the authored contract (worker and manager); MCP tool list includes `pull_request_checks` | `test_api_contract_parity.py`, `test_mcp_integration.py` |
| T7 | Unit (gate) | yes | `classify` for every row of the design's table; `CiBudget` counts distinct SHAs, repeats a counted SHA's attempt, delivers the exhausted notice once, drops afterwards, resets on a pass, ignores `cancelled`, evicts the least recently seen key; `render_section` names check, SHA, PR, attempt and the `pr checks` command | `cli/tests/test_cimonitor.py` |
| T8 | Integration (Gherkin, dispatcher) | yes | through `Dispatcher.handle` with a registered session and `FakeTmux`: a failing `check_run` is delivered with the CI section; a success, an in-progress run and a `workflow_run` are not delivered and are recorded `ci-not-actionable`; the fourth failing commit delivers the "stop and escalate" frame and the fifth is dropped `ci-autofix-exhausted`; a pass resets; `autofix: false` delivers every CI event with no section; a non-CI event's prompt is unchanged; an unmatched CI event takes the unmatched path | `cli/tests/test_ci_autofix_integration.py` |
| T9 | Config | yes | `routing.ci` parses with defaults; schema accepts it and rejects `maxAttempts: 0`; both schema copies identical; docs parity covers the new leaves | `test_cimonitor.py`, `test_config_schema_parity.py`, `test_docs_parity.py`, `scripts/validate_config.py` |
| T10 | Regression (full suite + hooks) | yes | ruff, ruff format, pyright, all CLI tests, markdownlint, config validation | `make check` equivalents |
| T11 | Security | yes (review) | no token to the log host, https only, logs never in the event prompt, bounded reads, every drop logged | `evidence/security-review.md` |
| T12 | UI / accessibility / snapshot / migration / performance | n/a | no UI; no stored data (the budget is in memory); at most 3 + 2×5 requests per `pr checks` call | |

## Requirement trace

| Requirement | Tests |
|-------------|-------|
| R1.1–R1.3, R1.6, R1.7 | T2, T3, T4, T5 |
| R1.4, R1.5 | T1, T2 |
| R2.1 | T4 |
| R2.2, R2.3, R2.4 | T5, T6 |
| R3.1, R3.2 | T7, T8 |
| R3.3, R3.4 | T8 |
| R4.1–R4.7 | T7, T8 |
| R5 | review of the doc diff (`evidence/documentation.md`) |
| Security considerations | T1, T3, T11 |

## Verification environment

This repository's own checkout; no service, fixture or credential beyond the test
suite. GitHub is `ghfakes.FakeGitHubClient` for core, CLI, service and dispatcher tests,
and the `github_replay` HTTP double for the client test, with the signed-URL download
replaced by a stub (the suite refuses real sockets).

## Not covered by an automated test

The live round trip against github.com: a real job log redirect, and a real failing
check waking a session. The replay test pins the request shapes; the live check is this
pull request's own CI the next time a check fails on a the-loop-driven PR.
