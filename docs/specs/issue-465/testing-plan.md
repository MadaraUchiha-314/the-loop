---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#465"
status: in-review
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: `the-loop pr ready`

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md). The
> results are in [`evidence/verification.md`](evidence/verification.md).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (client) | yes | `mark_pull_ready` sends the `markPullRequestReadyForReview` mutation with the node id as a variable, returns `not isDraft`, and refuses an unusable id before any request | `cli/tests/test_ghapi.py -k ready` |
| T2 | Unit (core) | yes | a draft PR of a registered work item is marked ready (exit 0, `changed: true`, event emitted); an already-ready PR is a no-op; a closed or merged PR is exit 1 with no write; a still-draft answer and a GitHub refusal are exit 1 | `cli/tests/test_github_ops.py -k ready` |
| T3 | Unit (abuse) | yes | an unowned PR is refused before any request; an untrusted host is a `ValueError` before any request; a bare number without `--work-item` is a `ValueError` | same |
| T4 | CLI | yes | `the-loop pr ready 12 --work-item …` prints the line and exits 0 in-process | `cli/tests/test_github_verbs_cli.py -k ready` |
| T5 | Integration (Gherkin) | yes | the route through the real service app marks a registered work item's draft ready and refuses an unowned PR | `cli/tests/test_github_verbs_integration.py -k ready` |
| T6 | Contract | yes | the served OpenAPI surface equals the authored contract (worker and manager); the MCP tool list includes `mark_pull_request_ready` | `cli/tests/test_api_contract_parity.py`, `cli/tests/test_mcp_integration.py` |
| T7 | Regression (full suite + hooks) | yes | ruff, ruff format, pyright, all CLI tests, markdownlint | `make check` equivalents |
| T8 | Security | yes (review) | guard before request, node id from GitHub not the caller, trusted hosts | `evidence/security-review.md` |
| T9 | UI / accessibility / snapshot / migration / performance | n/a | no UI, no stored data, at most two requests per call | |

## Requirement trace

| Requirement | Tests |
|-------------|-------|
| R1.1, R1.6 | T2, T4, T5 |
| R1.2 | T3, T4 |
| R1.3, R1.4, R1.5 | T2 |
| R2.1 | T4 |
| R2.2, R2.3 | T5, T6 |
| R2.4 | T6 (manager role serves the route); the proxy is the same `_acting_member` path as `pr merge` |
| R2.5 | T2 |
| R3.1, R3.2 | review of the doc diff (`evidence/documentation.md`) |
| Security considerations | T3, T8 |

## Verification environment

This repository's own checkout; no service, fixture or credential beyond the test
suite. GitHub is `ghfakes.FakeGitHubClient` for core and CLI tests and the
`github_replay` HTTP double for the client test.

## Not covered by an automated test

The live mutation against github.com. The replay test pins the exact GraphQL document
and variables; the live check is the next draft PR the-loop opens.
