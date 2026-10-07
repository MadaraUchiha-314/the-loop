---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#475"
---

# Unit and contract tests (T1–T5, T7, T8, issue-475)

Run on 2026-10-06 on branch `feat/issue-475-jira-5-edges` at `b5c1154` (the top of the
five-PR stack), with uv 0.12.10. Every command ran from `cli/` and was prefixed with
`env -u THE_LOOP_CLI_CONFIG -u THE_LOOP_WORK_ITEM -u THE_LOOP_GH_TOKEN` (see
[`verification.md`](verification.md) for why). The suite's autouse fixture refuses any
real socket, so Jira is `FakeJiraClient` throughout.

| Row | Files | Result |
|-----|-------|--------|
| T1 | `test_jira_refs.py`, `test_routing.py`, `test_graph_refs.py`, `test_graphlink.py`, `test_core_graphs.py` | 394 passed in 2.37s |
| T2 | `test_jira_api.py`, `test_jira_labels.py`, `test_jira_format.py` | 78 passed in 0.71s |
| T3 | `test_integration_contract.py`, `test_jira_integration_provider.py` | 32 passed in 0.17s |
| T4 | `test_jira_channels.py`, `test_channels.py`, `test_graph_integrations.py` | 173 passed in 1.17s |
| T5 | `test_jira_poller.py`, `test_jira_webhook.py`, `test_jira_authz.py` | 115 passed in 6.10s |
| T7 | the plan's `-k` expression over the whole suite | 67 passed, 5883 deselected in 7.85s |
| T7 | the twelve named abuse-case tests, by name | 25 passed (parametrized cases included), 0 failed |
| T8 | `test_migrations.py`, `test_config_schema_parity.py`, `test_jira_config.py` | 108 passed in 3.51s |

Every file the plan names exists. Three more Jira files were added by the PRs and are not
named in the plan's rows: `test_jira_linkage.py`, `test_jira_verbs.py` and
`test_doctor_jira.py`. They run in T9's full suite, and on their own give 38 passed.

## Trace names

Every test the trace table names exists, except two whose names differ:

- **T1 `test_github_refs_unchanged`** stands for "the existing tests, unmodified". No test
  has that name. The GitHub tests in the four existing T1 files are unchanged. The stack
  edits four lines there, and all four swap an old placeholder Jira ref for a GitHub-free
  one: three in `test_graphlink.py` now use `gitlab:acme/proj#42` for "another provider",
  and one in `test_routing.py` now uses the new `jira:<site>/<KEY>-<n>` grammar. No
  GitHub assertion changed.
- **T8 `test_migrate_is_idempotent`** is `test_migrate_jira_stub_is_idempotent` in
  `test_migrations.py`.

The test-first (red→green) history is in the PRs' commits. This run is the green half
only.

## T1

```text
$ cd cli && uv run python -m pytest -q tests/test_jira_refs.py tests/test_routing.py tests/test_graph_refs.py tests/test_graphlink.py tests/test_core_graphs.py
........................................................................ [ 91%]
..................................                                       [100%]
394 passed in 2.37s
```

## T2

```text
$ cd cli && uv run python -m pytest -q tests/test_jira_api.py tests/test_jira_labels.py tests/test_jira_format.py
........................................................................ [ 92%]
......                                                                   [100%]
78 passed in 0.71s
```

## T3

```text
$ cd cli && uv run python -m pytest -q tests/test_integration_contract.py tests/test_jira_integration_provider.py
................................                                         [100%]
32 passed in 0.17s
```

## T4

```text
$ cd cli && uv run python -m pytest -q tests/test_jira_channels.py tests/test_channels.py tests/test_graph_integrations.py
........................................................................ [ 83%]
.............................                                            [100%]
173 passed in 1.17s
```

## T5

```text
$ cd cli && uv run python -m pytest -q tests/test_jira_poller.py tests/test_jira_webhook.py tests/test_jira_authz.py
........................................................................ [ 62%]
...........................................                              [100%]
115 passed in 6.10s
```

## T7

The plan's expression:

```text
$ cd cli && uv run python -m pytest -q -k "jira and (reject or absent or unlisted or self_comment or alone or quoted or invalid_project or does_not_link or unknown_site or no_secret or untrusted)"
...................................................................      [100%]
67 passed, 5883 deselected in 7.85s
```

Each abuse case's named test, run by name with `-v`. All twelve names exist. No name is
missing.

| Abuse case | Test | Where | Result |
|------------|------|-------|--------|
| 1 | `test_jira_webhook_rejects_bad_signature` | `test_jira_webhook.py` | passed (4 parametrized cases) |
| 2 | `test_jira_webhook_absent_without_secret` | `test_jira_webhook.py` | passed |
| 3 | `test_jira_comment_from_unlisted_author_is_ignored` | `test_jira_authz.py` | passed |
| 4 | `test_jira_self_comment_never_resumes` (`marker` and `author` variants) | `test_jira_channels.py` | passed (2 cases) |
| 5 | `test_jira_label_alone_does_not_start` | `test_jira_integration.py` (and `…_by_webhook` in `test_jira_webhook.py`) | passed |
| 6 | `test_jql_values_are_quoted` | `test_jira_poller.py` | passed (4 cases) |
| 6 | `test_invalid_project_key_fails_config` | `test_jira_config.py` | passed (5 cases) |
| 7 | `test_pr_naming_unregistered_jira_key_does_not_link` | `test_jira_linkage.py` | passed |
| 7 | `test_pr_in_other_repository_does_not_link` | `test_jira_linkage.py` | passed |
| 8 | `test_ref_on_unknown_site_sends_no_credential` | `test_jira_refs.py` and `test_jira_integration_provider.py` | passed |
| 9 | `test_jira_errors_and_logs_carry_no_secret` | `test_jira_api.py` | passed |
| 10 | `test_jira_comment_is_framed_untrusted` | `test_jira_integration.py` | passed |

```text
$ cd cli && uv run python -m pytest -v -k "<the twelve names joined by or>"
...
===================== 25 passed, 5925 deselected in 5.92s ======================
```

## T8

```text
$ cd cli && uv run python -m pytest -q tests/test_migrations.py tests/test_config_schema_parity.py tests/test_jira_config.py
........................................................................ [ 66%]
....................................                                     [100%]
108 passed in 3.51s
```
