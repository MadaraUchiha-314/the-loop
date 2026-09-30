---
type: testing-plan
phase: test-planning
workItem: "issue-442"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: the daemon reaches GitHub through PyGithub

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only. No test touches the network: the client is exercised through
> PyGithub's connection-injection hook with canned exchanges, the callers through a fake
> client.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit — the client | yes | `test_ghapi.py` against the replaying connection: for each of O1–O12 the verb, path, JSON body and `Authorization: Bearer` header PyGithub sends; the enterprise base (`https://ghe/api/v3`, GraphQL at `/api/graphql`) and the configured `baseUrl`; pagination through `Link` (reviews, review comments, issues past one page) and the 200 cap; the GraphQL PR listing's variables and cursor walk; node-id comment ids and `Z` timestamps; every error class (`missing_token`, 401, 404 → `not_found`, 410, 422/404 idempotence, GraphQL `errors`, a `requests` transport error, a timeout) translated to `GitHubApiError`; the per-`(host, token)` cache and `shared()`; coordinate refusals before any request | `uv run --project cli python -m pytest -q cli/tests/test_ghapi.py` |
| T2 | Unit — the writers | yes | `test_comments.py`, `test_linkage.py`, `test_reactions.py`, `test_announce.py`, `test_selfdiagnosis.py`: the same contracts as today re-expressed over the fake client — ok/error tuples, never raises, the one 404, warn-once on a missing token, non-GitHub refs and bad coordinates refused before a call, `ReactionTarget` kinds, `html_url`s and issue numbers passed through | `uv run --project cli python -m pytest -q cli/tests/test_comments.py cli/tests/test_linkage.py cli/tests/test_reactions.py cli/tests/test_announce.py cli/tests/test_selfdiagnosis.py` |
| T3 | Unit — the readers and config | yes | `test_poller.py`: the provider over the fake client (listings, labels re-check, three PR surfaces merged chronologically, closure state, issues-disabled classification by 410 and by text, `check_dependencies` naming the variables); `test_graph_integrations.py`: one provider, `resolve` on `auto`/`api`, `cli` refused by name, missing token names the variables, hosted refs; `test_cli_config.py`/`test_control.py`: the `_github` fan-out; `test_sdk_environment.py`: no `gh` row | `uv run --project cli python -m pytest -q cli/tests/test_poller.py cli/tests/test_graph_integrations.py cli/tests/test_cli_config.py cli/tests/test_control.py cli/tests/test_sdk_environment.py` |
| T4 | Integration (scenario) | yes | Gherkin scenarios through the real modules with the fake client at the process boundary: `test_poller_integration.py` (a labelled issue polled, commented, closed; a PR's reviews forwarded; a give-up notice posted), `test_reactions_integration.py`, `test_tmux_runner_integration.py` (the announcement), `test_selfdiagnosis_integration.py` (an issue filed, dry-run files nothing), `test_channels_integration.py` and the other channel scenarios (ledger writes with `api=`), `test_control_integration.py`, `test_webhook_routing_integration.py` (a branch-invented ref dropped on 404 only) | `uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py cli/tests/test_reactions_integration.py cli/tests/test_tmux_runner_integration.py cli/tests/test_selfdiagnosis_integration.py cli/tests/test_channels_integration.py cli/tests/test_control_integration.py cli/tests/test_webhook_routing_integration.py` |
| T5 | Contract / parity | yes | the authored and packaged schemas byte-identical (`test_config_schema_parity.py`); every documented option exists and every schema leaf is documented after the removal (`test_docs_parity.py` P3/P4); `docs/sdk/environment.md` lists every requirement and nothing more (`test_sdk_docs_parity.py`); `pyproject` ↔ lockfile (`uv sync --locked`) | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_sdk_docs_parity.py` and `uv sync --locked` |
| T6 | Migration / upgrade | yes | `test_migrations.py`: a 0.10.0 config carrying `transport: cli` and `cli.binary` migrates to 0.11.0 with both keys gone, two moves and the token note; a config with `transport: api` and `tokenEnv` set migrates with no note; idempotent; a 0.10.0 file still carrying a per-feature `ghBinary` migrates in one step; an un-migrated file is refused naming the key and the command; `CURRENT_CONFIG_VERSION == "0.11.0"`; every test fixture that writes a current config writes `0.11.0` | `uv run --project cli python -m pytest -q cli/tests/test_migrations.py` and the full suite |
| T7 | Security / abuse case | yes | one negative test per abuse case A1–A8 (`design.md` § Security design): the token absent from every reason string and log record on a 401 (A1); a hostile owner/repo/number/node id refused before any exchange (A2); a ref with a non-host third segment never builds a base (A3); no operation beyond the twelve (the provider's `operations` set unchanged) (A4); a `Github` built with `retry=2`, the caller's timeout and no `GithubRetry` (A5); the GraphQL documents are constants and the payload text arrives only in `variables` (A6); every posted body still carries the marker (A7, existing tests); the warn-once, pre-flight and refusal on a missing token (A8) | `uv run --project cli python -m pytest -q cli/tests -k "token_never or hostile or not_a_host or operations_unchanged or no_rate_limit_sleep or graphql_variables or missing_token"` |
| T8 | Performance / load | yes, bounded | the per-cycle request count of a poll over one repository with one issue and one PR is `2 + 1 + 3` exchanges, asserted on the replaying connection's log; a comment write reuses the same connection object across two calls of the shared client | `uv run --project cli python -m pytest -q cli/tests/test_ghapi.py -k "request_count or reuses"` |
| T9 | End-to-end | n/a — every real process boundary the daemon has (tmux, the service, the event log) is already covered by the existing integration suites, which run unchanged over the fake client; a live GitHub exchange is the manual row below | | |
| T10 | Manual exploratory | yes | on a box **without** `gh`: `pip install` the built wheel, export a token, run `the-loop start` with polling enabled against a scratch repository, label an issue, comment `the-loop start`, watch the reaction, the announcement and the paper-trail comment land, close the issue and watch the closure detected; then unset the token, restart, and read the warnings; recorded as evidence | procedure in `evidence/manual.md` |
| T11 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T12 | Security review (gate) | yes | the-loop checklist against A1–A8, recorded as evidence; tier 4 needs a **named human sign-off** — the owner's, at the PR | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R3.1 (O1–O12), R3.2, R3.3, R5.1 | each operation's exact exchange; hosts; pagination; error classes; no rate-limit sleep |
| T2 | R2.3, R3.1 (O1–O5), R5.1 | best-effort tuples; warn once; the one 404; refusals before a call |
| T3 | R1.2, R2.3, R3.1 (O6–O11), R3.4, R4.3 | provider listings and classification; the graph's one provider; the fan-out; the environment table |
| T4 | R3.1, R3.2, R5.1 | `Scenario: A labelled issue is polled, commented and closed through PyGithub` and siblings, named in the test files |
| T5 | R4.1, R4.4, R1.1 | schema parity; docs parity; lockfile |
| T6 | R4.1, R4.2 | the migration both ways; idempotence; the token note |
| T7 | A1–A8 | one negative test each |
| T8 | R5.2, NFR performance | request count; session reuse |
| T10 | R1.2, R2.1, R2.3 | a `gh`-less box end to end |

## Verification environment

The work item's cloud checkout: `uv 0.12.x`, Python 3.11, no `gh` on `PATH`, no network
in tests. The manual row needs a scratch repository and a token with *Issues: read/write*
and *Pull requests: read*; the evidence records the box and the outcome, never the token.

## Evidence to capture

- `evidence/verification.md` — one section per row, the command and the runner's summary
  line, red→green notes for the tests written first.
- `evidence/self-review.md`, `evidence/security-review.md`, `evidence/documentation.md`,
  `evidence/manual.md`, `evidence/reviewer-briefing.md`.

## Activities checklist

- [x] T1 written for O1–O12 against the replaying connection (the client was smoke-tested against it first; the two behaviours the tests then went red on — the URL stamp on an empty document and the eager completion of a URL-built object — are C1/C2 in `evidence/self-review.md`)
- [x] T2–T3 re-expressed over the fake client; the old fake-runner doubles deleted
- [x] T4 scenarios pass unchanged in intent
- [x] T5 parity green after the schema and docs edits
- [x] T6 migration both ways
- [x] T7 one test per abuse case
- [x] T8 request count asserted
- [x] T10 procedure recorded (`evidence/manual.md`; the live-repository steps are the owner's to run — not claimed)
- [x] T11 `make check` green
- [x] T12 checklist recorded; human sign-off requested on the PR

## Verification results

Filled at the `verification` node on 2026-09-30; the raw summaries are in
[`evidence/verification.md`](evidence/verification.md).

| Row | Command | Outcome | Artifact |
|-----|---------|---------|----------|
| T1 | `pytest tests/test_ghapi.py` | 49 passed | `cli/tests/test_ghapi.py`, `cli/tests/ghreplay.py` |
| T2 | the five writer suites | 116 passed | `cli/tests/test_{comments,linkage,reactions,announce,selfdiagnosis}.py`, `cli/tests/ghfakes.py` |
| T3 | the reader and config suites | 360 passed | `cli/tests/test_{poller,graph_integrations,cli_config,control,sdk_environment}.py` |
| T4 | the integration scenarios | 226 passed | the ten scenario suites; `cli/tests/ghstub.py` for the daemon ones |
| T5 | the parity suites; `uv sync --locked` | 12 passed; lockfile current | — |
| T6 | `pytest tests/test_migrations.py` | 64 passed | — |
| T7 | `pytest tests -k <abuse cases>` | 35 passed | `evidence/security-review.md` |
| T8 | `pytest tests/test_ghapi.py -k "six_requests or reuses"` | 2 passed | — |
| T10 | procedure | the `gh`-less steps run; the live-repository steps left to the owner | `evidence/manual.md` |
| T11 | `make check` (each target run from the root) | all green; the full suite 5020 passed, 1 skipped | — |
| T12 | the checklist | no open finding; human sign-off requested on the PR | `evidence/security-review.md` |
