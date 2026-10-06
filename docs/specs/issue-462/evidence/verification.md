---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#462"
---

# Verification (issue-462)

Run on 2026-10-06 on branch `claude/github-issue-462-r9n2t7`, using uv 0.12.23 (the
repository requires `>=0.12,<0.13`). GitHub is `ghfakes.FakeGitHubClient` for core,
CLI, service and dispatcher tests, and the `github_replay` HTTP double for the client
test, with the signed-URL download replaced by a stub (`ghapi._urlopen`). The suite's
autouse fixture refuses any real socket.

## Activities

- [x] T1–T6 and T7–T8 written first and seen red against the code before the change.
- [x] T1–T9 green after the change.
- [x] T10 full suite, ruff (lint and format), pyright, markdownlint, config validation.
- [x] T11 security review (`security-review.md`).

## T1–T6: red before the change

```text
$ cd cli && uv run python -m pytest -q -k "462 or job_log or github_verbs_are_tools" \
    tests/test_ghapi.py tests/test_github_ops.py tests/test_github_verbs_cli.py \
    tests/test_github_verbs_integration.py tests/test_mcp_integration.py
FAILED tests/test_ghapi.py::test_issue_462_job_log_tail_reads_the_redirect_and_fetches_it_without_the_token
FAILED tests/test_ghapi.py::test_issue_462_a_long_log_keeps_only_its_tail_and_says_when_it_was_cut
FAILED tests/test_ghapi.py::test_abuse_462_a_log_redirect_that_is_not_https_is_refused
FAILED tests/test_ghapi.py::test_abuse_462_a_bad_job_id_is_refused_before_any_request
FAILED tests/test_ghapi.py::test_issue_462_a_job_without_a_log_is_an_error_with_githubs_status
FAILED tests/test_github_ops.py::test_issue_462_pr_checks_lists_every_check_with_the_failing_logs
FAILED tests/test_github_ops.py::test_issue_462_pr_checks_failing_filters_and_log_lines_0_fetches_no_log
FAILED tests/test_github_ops.py::test_issue_462_pr_checks_fetches_at_most_five_logs
FAILED tests/test_github_ops.py::test_issue_462_a_log_that_cannot_be_read_does_not_fail_the_read
FAILED tests/test_github_ops.py::test_issue_462_a_startup_failure_is_failing
FAILED tests/test_github_ops.py::test_issue_462_pr_checks_of_a_missing_pull_request_is_exit_1
FAILED tests/test_github_ops.py::test_issue_462_a_long_summary_is_capped - At...
FAILED tests/test_github_ops.py::test_abuse_462_pr_checks_refuses_before_any_request[12-]
FAILED tests/test_github_ops.py::test_abuse_462_pr_checks_refuses_before_any_request[github:evil.example/octo/repo#12-]
FAILED tests/test_github_ops.py::test_abuse_462_pr_checks_refuses_a_negative_log_line_count
FAILED tests/test_github_verbs_cli.py::test_issue_462_pr_checks_prints_the_failing_checks_with_their_logs
FAILED tests/test_github_verbs_integration.py::test_issue_462_the_service_lists_a_pull_requests_failing_checks
FAILED tests/test_mcp_integration.py::test_the_github_verbs_are_tools - Asser...
18 failed, 234 deselected in 2.46s
```

## T7–T8: red before the change

The gate's module did not exist, so both files failed at collection:

```text
$ cd cli && uv run python -m pytest -q tests/test_cimonitor.py tests/test_ci_autofix_integration.py
ERROR tests/test_cimonitor.py
ERROR tests/test_ci_autofix_integration.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
2 errors in 0.19s
```

## T1–T9: green after the change

```text
$ cd cli && uv run python -m pytest -q -k "462 or job_log or github_verbs_are_tools" \
    tests/test_ghapi.py tests/test_github_ops.py tests/test_github_verbs_cli.py \
    tests/test_github_verbs_integration.py tests/test_mcp_integration.py
18 passed, 234 deselected in 5.54s

$ cd cli && uv run python -m pytest -q tests/test_cimonitor.py \
    tests/test_ci_autofix_integration.py tests/test_api_contract_parity.py \
    tests/test_docs_parity.py tests/test_config_schema_parity.py tests/test_routing.py
260 passed in 5.33s
```

`test_api_contract_parity.py` is green only because the authored contract names `GET
/api/v1/pull-requests/checks` (`listPullRequestChecks`). `test_docs_parity.py` is green
only because `routing-options.md` documents `ci.autofix` and `ci.maxAttempts` with
their type and default. `test_routing.py`'s settled-vocabulary test was extended with
the two `ci-*` outcomes, as its docstring requires of a new settlement.

## T10: the full suite and the hooks

```text
$ cd cli && uv run python -m pytest -q
5472 passed, 1 skipped, 4 warnings in 245.38s (0:04:05)

$ uv run ruff check cli hooks
All checks passed!

$ uv run ruff format --check cli hooks
417 files already formatted

$ uv run pyright cli
0 errors, 0 warnings, 0 informations

$ npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Summary: 0 error(s)

$ uv run python scripts/validate_config.py
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

## Results

| Activity | Command | Outcome | Evidence |
|---|---|---|---|
| T1 client | `pytest tests/test_ghapi.py -k 462` | pass (red first) | above |
| T2 core | `pytest tests/test_github_ops.py -k issue_462` | pass (red first) | above |
| T3 abuse | `pytest tests/test_github_ops.py -k abuse_462` | pass (red first) | above |
| T4 CLI | `pytest tests/test_github_verbs_cli.py -k 462` | pass (red first) | above |
| T5 integration | `pytest tests/test_github_verbs_integration.py -k 462` | pass (red first) | above |
| T6 contract / MCP | `test_api_contract_parity.py`, `test_mcp_integration.py` | pass (MCP red first) | above |
| T7 gate unit | `pytest tests/test_cimonitor.py` | pass (red first) | above |
| T8 gate integration | `pytest tests/test_ci_autofix_integration.py` | pass (red first) | above |
| T9 config | `test_cimonitor.py -k schema`, parity tests, `validate_config.py` | pass | above |
| T10 regression | full suite + hooks | pass | above |
| T11 security | review | pass | [`security-review.md`](security-review.md) |
| T12 | — | n/a | no UI, no stored data |
