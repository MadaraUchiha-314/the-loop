# Security review (issue-442)

Tier 4. the-loop's checklist over the requirements' abuse cases, run on the branch diff
against `4fd746a` on 2026-09-30, scoped to `cli/the_loop`. The one change to the threat
model is named first: **the daemon holds a GitHub credential of its own** — a token in its
environment — where it used to borrow the operator's `gh` login. Everything below is about
keeping that token where it is and making sure the move added no capability.

## The checklist — abuse case → mechanism → negative test

| # | Abuse case | Mechanism | Test | Verdict |
|---|------------|-----------|------|---------|
| A1 | the token leaks through a log line, an event, a comment body or an error string | the token is read inside `GitHubClient.github()` and handed to `Auth.Token`; every `GitHubApiError` is composed from the status and GitHub's `message`; the `the-loop.ghapi` debug log records verb, path and status | `test_the_token_never_appears_in_a_reason_or_a_log_line` | holds |
| A2 | payload-derived coordinates reach a URL path or a GraphQL variable unvalidated | `comments`/`linkage`/`reactions` keep their `_NAME_RE`/`is_github_name` checks; the client re-validates owner/repo, refuses a non-positive or non-integer number/id and a node id outside `[A-Za-z0-9_=+/-]` before any request | `test_hostile_coordinates_never_reach_a_request`, `test_a_bad_number_never_reaches_a_request`, `test_reactions_refuse_an_unknown_content_or_a_bad_target_before_any_request`, `test_hostile_coordinates_never_reach_the_client` (linkage) | holds |
| A3 | a hostile host inside a ref points the client (and the token) at another API | `github(host)` asserts `is_github_host` and derives the base with `ghhost.api_base_for`; an explicit `baseUrl` is the operator's | `test_a_value_that_is_not_a_host_never_builds_a_base`, `test_an_explicit_enterprise_base_is_honoured_for_every_host` | holds |
| A4 | an over-scoped token widens what a prompt-injected comment can make the-loop do | the graph provider's `operations` set is the same seven; the poller and writers perform the same twelve operations; the docs name the minimum scopes | `test_the_operations_are_unchanged`, `test_the_provider_no_longer_answers_which_pulls_a_work_item_links` | holds |
| A5 | a rate-limited or slow GitHub stalls a poll cycle or a dispatch thread | `Github(retry=2, timeout=<caller's>)`, no `GithubRetry`, no courtesy sleeps | `test_the_github_is_built_without_a_rate_limit_sleep` | holds |
| A6 | GraphQL text built from payload data | the three documents are module constants; owner, name, number, labels, cursor and node id travel as variables | `test_a_node_reaction_is_the_graphql_mutation_with_variables`, `test_list_labeled_issues_is_the_graphql_query_gh_ran` | holds |
| A7 | a comment the-loop posts is read back as human input | unchanged: every body still carries the self-authored marker; `viewer_login` is the token's login and the ledger reads its own records by it | existing marker tests (`test_body_is_marked_as_the_loops_own`, `test_giveup_notice_says_what_happened_and_what_to_do`), `test_a_pasted_record_from_another_author_is_not_listed` | holds |
| A8 | an upgraded deployment silently posts as nobody | one warning per process per writer, the poller's pre-flight, the graph's refusal and the migration's note | `test_missing_token_warns_once` (announce), `test_reactor_missing_token_noops_and_warns_once`, `test_no_token_keeps_every_ref_and_warns_once`, `test_check_github_credentials_reports_when_the_token_is_missing`, `test_a_missing_token_fails_closed_naming_the_variables`, `test_migration_retires_both_keys_and_notes_the_token_after_a_cli_transport` | holds |

## What else was checked

- **No shell anywhere.** The diff removes every `subprocess` call that reached GitHub;
  `shutil.which` is gone from the GitHub path. The only subprocess left in the touched
  modules is the critic runner in `core/selfdiagnosis.py`, untouched.
- **No token in configuration.** `tokenEnv` holds variable names; the schema description
  says so; `GitHubApiConfig.to_mapping()` (the `_github` fan-out) carries names and the
  base URL, never a value.
- **The test suite cannot leak a token or reach GitHub.** `conftest.py` deletes
  `GH_TOKEN`/`GITHUB_TOKEN` for every test and installs a connection class that fails any
  HTTP PyGithub attempts; the daemon integration tests point the child processes at a
  loopback server. Before this change two graph tests passed or failed with the machine's
  ambient token.
- **PyGithub's own behaviours reviewed:** it masks `Authorization` in its debug logging;
  its default `GithubRetry` (a sleep until the rate-limit reset) is not used; the
  `requests` session verifies TLS by default and `verify` is left at `True`; redirects are
  not followed by the connection class (`allow_redirects=False`), and a `301` to another
  host is refused by the requester.
- **Dependency surface.** PyGithub 2.10.0 and its transitive set (`requests`, `urllib3`,
  `pynacl`, `pyjwt`, `typing-extensions`, `Deprecated`, `cffi`, `cryptography`,
  `charset-normalizer`, `idna`, `certifi`, `wrapt`) are pinned in `uv.lock`; nothing in the
  daemon imports `pynacl`/`pyjwt` (they serve PyGithub's App and secret features, unused).

## Findings

None open. One posture note: the token grants what its scopes grant on every repository
the instance works with, which is the same reach the operator's `gh` login had — the
docs name the minimum scopes so an operator can mint a narrower one than they log in with.

**Tier 4 requires a named human security sign-off at the PR — the owner's.** Requested in
the PR description; this record is updated with the name and date when it lands.
