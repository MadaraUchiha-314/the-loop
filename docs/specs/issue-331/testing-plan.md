---
type: testing-plan
phase: test-planning
workItem: "issue-331"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: a poll source's bare `OWNER/REPO` is on the GitHub the-loop resolves

> Derived from `bugfix.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; no
> credentials are involved.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `RepoSpec.parse` / `parse_repos` with a default host (inherited, explicit wins, github.com unwritten, malformed refused, de-duplicated); `from_source` and `build_provider` carry `default_host`; the ticket's `owns()` regression and its negative half; `describe()` names the host; `daemon._build_providers` resolves the host from the CLI config and from `$GH_HOST` | `uv run --project cli python -m pytest -q cli/tests/test_poller.py -k "default_host or inherit or describe or resolved_host"` |
| T2 | Integration (scenario) | yes | `Scenario: A closed item on a bare enterprise source is reconciled` — through `poll_once`, a tracked item on a source declared `octo/repo` under a resolved enterprise host disappears from the listing, reads as closed on that host, is stamped `ended` and closed through the dispatcher | `uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py -k enterprise` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no route or schema changes | | |
| T4 | End-to-end | n/a — the daemon's process boundary is exercised by the existing `test_poll_daemon_integration.py`, which is unchanged by this fix; the host resolution it now performs is unit-tested at the helper | | |
| T5 | UI / visual | n/a — no user-facing surface | | |
| T6 | Snapshot | n/a — assertions on argv, specs and records | | |
| T7 | Performance / load | n/a — one resolver call per plan build, no per-cycle cost | | |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A3 (`bugfix.md` § Security considerations); A4 by construction | `uv run --project cli python -m pytest -q cli/tests/test_poller.py -k "malformed_default_host or inherits_the_default_host or github_com"` |
| T9 | Accessibility | n/a — no user-facing surface | | |
| T10 | Migration / upgrade | yes | a github.com deployment is byte-identical: the issue-311 host tests and every pre-existing poller test unchanged and green | `uv run --project cli python -m pytest -q cli/tests/test_poller.py cli/tests/test_poller_integration.py` |
| T11 | Manual exploratory | n/a — no GitHub Enterprise deployment is reachable from this session; the reviewer's walk-through is the PR briefing's "what to check" | | |
| T12 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T13 | Security review (gate) | yes | the-loop checklist against A1–A4, recorded as evidence; tier 3 needs no human sign-off | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.3 | `test_repospec_inherits_a_default_host_unless_it_names_its_own` |
| T1 | R1.2 | `test_a_github_com_default_leaves_the_spec_unwritten` |
| T1 | A1 | `test_repospec_refuses_a_malformed_default_host` |
| T1 | R1.1 | `test_parse_repos_dedupes_an_inherited_host_against_a_written_one` |
| T1 | R1.1, R1.3 | `test_provider_from_source_binds_bare_repos_to_the_default_host` |
| T1 | R1.1 | `test_build_provider_carries_the_default_host` |
| T1 | R1.4, R2.1, A2 | `test_a_bare_repo_inherits_the_default_host_and_owns_its_refs` (the ticket's assertion, inverted, plus the github.com twin refused) |
| T1 | R1.4 | `test_a_bare_repos_reads_go_to_the_inherited_host` (listing `--repo`, closure `--hostname`, `scope_of`) |
| T1 | R1.6 | `test_describe_names_the_host_a_source_is_bound_to` |
| T1 | R1.1, R1.5 | `test_the_daemon_binds_sources_to_the_resolved_host[integrations.github.host / GH_HOST / none]` |
| T2 | R2.2 | `Scenario: A closed item on a bare enterprise source is reconciled` |
| T8 | A1–A3 | the negative tests named above |
| T10 | A3 | the issue-311 host tests, `test_build_provider_constructs_github` (`describe()` for github.com unchanged) |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. `gh` is faked at its injection point (`GhClient`'s
  `runner`); the daemon helper is handed a config mapping and `$GH_HOST` is monkeypatched.
- **Fixtures & data:** temp directories per test; `ghe.corp.example` as the host.
- **Credentials:** none.
- **Bring-up:** `uv sync` · **Tear-down:** none.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T10, T12 | command, counts, raw tail of the output; red → green | `verification.md` |
| T13 | the abuse-case table with verdicts and the tests that close each | `security-review.md` |

## Verification activities

- [x] T1 — the unit selection above
- [x] T2 — the integration scenario
- [x] T8 — the abuse-case selection
- [x] T10 — the two poller suites in full
- [x] T12 — `make check`
- [x] T13 — `evidence/security-review.md`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_poller.py -k "default_host or inherit or describe or resolved_host"` | pass — 15 passed (all new; red first) | [`evidence/verification.md`](evidence/verification.md) |
| T2 | `uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py -k enterprise` | pass — 1 passed (new; red first) | [`evidence/verification.md`](evidence/verification.md) |
| T8 | `… -k "malformed_default_host or inherits_the_default_host or github_com"` | pass — 7 passed (A1–A3) | [`evidence/verification.md`](evidence/verification.md), [`evidence/security-review.md`](evidence/security-review.md) |
| T10 | `uv run --project cli python -m pytest -q cli/tests/test_poller.py cli/tests/test_poller_integration.py` | pass — 232 passed, no pre-existing assertion changed | [`evidence/verification.md`](evidence/verification.md) |
| T12 | `make check` | pass — 3182 passed, 1 skipped; ruff, markdownlint, pyright and the config validation clean | [`evidence/verification.md`](evidence/verification.md) |
| T13 | the-loop checklist over A1–A4 | pass; no human sign-off at tier 3 | [`evidence/security-review.md`](evidence/security-review.md) |

**Not executed:** none.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed.
