---
type: testing-plan
phase: test-planning
workItem: "issue-447"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: the harness's GitHub verbs

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`. The results section is filled at `verification`.
>
> **This file is executable content.** The commands below are what the agent runs.
> Credentials appear by reference only. No test touches the network: the client is
> exercised over `ghreplay`'s replaying connection, and core and the commands over
> `FakeGitHubClient`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit: the client | yes | `test_ghapi.py`: each new method's exact verb, path, query and JSON body. The GraphQL `reviewThreads` document gets its variables and cursor walk tested. Hostile branch, SHA, method and coordinates are refused before any exchange. A 422 on `create_pull` and a 405 on `merge_pull` become `GitHubApiError` | `uv run --project cli python -m pytest -q cli/tests/test_ghapi.py` |
| T2 | Unit: core | yes | `test_github_ops.py`: each operation over the fake client. Covered: data fields and exit codes; the comment published as `comment.agent` with `record=True` and a marked, enveloped body; the direct-post fallback when the bus raises; the checks roll-up table (success, failure, pending, none, statuses and runs mixed); resolved threads filtered; merge refused when `mergeOnApproval: false`; `pr create` defaulting base and repository, linking, and still exiting 0 when the link fails; `--discover` linking every PR found, and none found; the PR-argument grammar | `uv run --project cli python -m pytest -q cli/tests/test_github_ops.py` |
| T3 | Unit: CLI commands and routing | yes | `test_github_verbs_cli.py`: argument groups (`--body` or `--body-file`, `--pull-request` or `--discover`), `--body-file -` from stdin, JSON output of `show`, `status` and `threads`, a detached HEAD refused, exit codes 0, 1 and 2. `harness_routed`: remote when healthy, local with the stderr note when not, never auto-started | `uv run --project cli python -m pytest -q cli/tests/test_github_verbs_cli.py` |
| T4 | Integration (scenario) | yes | `test_github_verbs_integration.py`, with Gherkin docstrings: a comment reaches the ledger and a subscribed fake channel, and the poller-side publisher then drops it as enveloped; a PR opened by `pr create` lands in the session registry and in `work-item-state.json`; the service's routes answer each operation through `TestClient` with the fake client | `uv run --project cli python -m pytest -q cli/tests/test_github_verbs_integration.py` |
| T5 | Contract / parity | yes | `test_api_contract_parity.py`: the authored OpenAPI file carries every new path, method and operationId for both roles; the MCP tool list is the same for both roles; `test_standing_security_integration.py`'s tool list is updated; `test_docs_parity.py`: every new command has a page | `uv run --project cli python -m pytest -q cli/tests/test_api_contract_parity.py cli/tests/test_standing_security_integration.py cli/tests/test_docs_parity.py` |
| T6 | Unit: the hook | yes | `test_harness_link_pr.py`: `git push`, `gh pr create`, `hub pull-request`-shaped and MCP `create_pull_request` calls each run `link-pr --discover` with the resolved work item; `the-loop pr create`, an unrelated `Bash` call and an interrupted call run nothing; no response text reaches the argv; every path exits 0 | `uv run --project cli python -m pytest -q cli/tests/test_harness_link_pr.py` |
| T7 | Security / abuse case | yes | one negative test per abuse case: the token is absent from a failing verb's output (A1); merge is refused under `mergeOnApproval: false`, and the route body cannot carry a policy (A2); hostile coordinates are refused before an exchange (A3); the comment is marked and enveloped (A4); the fallback note is printed (A5); the hook uses no shell and passes no response text (A6); `ticket show` fetches no attachment (A7) | `uv run --project cli python -m pytest -q cli/tests -k "abuse_447"` |
| T8 | Performance | yes, bounded | `pr status` makes exactly three exchanges on the replaying connection | part of T1 |
| T9 | End-to-end | n/a | a live GitHub exchange needs a token and a scratch repository this cloud session does not hold. Every process boundary (CLI to service to core to client) is covered by T3 and T4 | |
| T10 | Manual exploratory | n/a | same reason as T9. The owner can run `the-loop pr status github:MadaraUchiha-314/the-loop#<this PR>` on a box with the daemon | |
| T11 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T12 | Security review (gate) | yes | the-loop's checklist against A1–A7, recorded as evidence. Tier 3: the autonomous review suffices | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.2–R1.8, NFR | each request's exact exchange; refusals before a request |
| T2 | R1.1–R1.9, R4.1 | each operation's result, exit code and error path |
| T3 | R1.*, R2.1–R2.3, R4.1–R4.2 | the argument grammar; the routing choice and its note |
| T4 | R1.1, R1.4, R3.1 | `Scenario: An agent's comment is recorded and mirrored, never re-published` and its siblings |
| T5 | R3.1, R3.2, R5.2 | contract, tools and docs parity |
| T6 | R4.3, R4.4 | the trigger table |
| T7 | A1–A7 | one negative test each |

## Verification environment

The work item's cloud checkout: `uv 0.12.x`, Python 3.11, no `gh` on `PATH`, no token,
and no network in tests.

## Evidence to capture

- `evidence/verification.md`: one section per row, with the command and the runner's
  summary line.
- `evidence/self-review.md`, `evidence/security-review.md`, `evidence/documentation.md`,
  and `evidence/reviewer-briefing.md` (also posted on the PR).

## Activities checklist

- [ ] T1 client
- [ ] T2 core
- [ ] T3 commands and routing
- [ ] T4 integration
- [ ] T5 parity
- [ ] T6 hook
- [ ] T7 abuse cases
- [ ] T11 `make check`
- [ ] T12 security review

## Verification results

*(filled at `verification`)*
