---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#465"
---

# Verification (issue-465)

Run on 2026-10-06 on branch `claude/github-issue-465-5b3d0f`, using uv 0.12.23 (the
repository requires `>=0.12,<0.13`) and Python 3.11. GitHub is
`ghfakes.FakeGitHubClient` for core, CLI and service tests, and the `github_replay`
HTTP double for the client test. The suite's autouse fixture refuses any real socket.

## Activities

- [x] T1–T5 written first and seen red against the code before the change.
- [x] T1–T6 green after the change.
- [x] T7 full suite, ruff (lint and format), pyright, markdownlint, config validation.
- [x] T8 security review (`security-review.md`).

## T1–T6: red before the change

The new tests against the code before `mark_ready` existed:

```text
$ cd cli && uv run python -m pytest -q -k "465 or mark_pull_ready or github_verbs_are_tools" \
    tests/test_ghapi.py tests/test_github_ops.py tests/test_github_verbs_cli.py \
    tests/test_github_verbs_integration.py tests/test_mcp_integration.py
E         Extra items in the left set:
E         'mark_pull_request_ready'
FAILED tests/test_ghapi.py::test_mark_pull_ready_is_the_mutation_with_the_node_id_as_a_variable
FAILED tests/test_ghapi.py::test_mark_pull_ready_reports_a_pull_request_still_in_draft
FAILED tests/test_github_ops.py::test_issue_465_pr_ready_marks_a_registered_work_items_draft_ready
FAILED tests/test_github_ops.py::test_issue_465_pr_ready_on_a_ready_pull_request_writes_nothing
FAILED tests/test_github_ops.py::test_issue_465_pr_ready_refuses_a_pull_request_that_is_not_open[fields0-merged]
FAILED tests/test_github_ops.py::test_issue_465_pr_ready_refuses_a_pull_request_that_is_not_open[fields1-closed]
FAILED tests/test_github_ops.py::test_issue_465_pr_ready_still_draft_after_the_mutation_is_exit_1
FAILED tests/test_github_ops.py::test_issue_465_pr_ready_refused_by_github_is_exit_1[get_pull]
FAILED tests/test_github_ops.py::test_issue_465_pr_ready_refused_by_github_is_exit_1[mark_pull_ready]
FAILED tests/test_github_ops.py::test_abuse_465_pr_ready_of_an_unowned_pull_request_asks_github_nothing
FAILED tests/test_github_ops.py::test_abuse_465_pr_ready_on_an_untrusted_host_is_refused_before_a_request
FAILED tests/test_github_verbs_cli.py::test_issue_465_pr_ready_marks_the_draft_ready
FAILED tests/test_github_verbs_integration.py::test_issue_465_the_service_marks_only_its_own_draft_ready
FAILED tests/test_mcp_integration.py::test_the_github_verbs_are_tools - Asser...
14 failed, 221 deselected in 2.20s
```

## T1–T6: green after the change

```text
$ cd cli && uv run python -m pytest -q -k "465 or mark_pull_ready or github_verbs_are_tools" \
    tests/test_ghapi.py tests/test_github_ops.py tests/test_github_verbs_cli.py \
    tests/test_github_verbs_integration.py tests/test_mcp_integration.py
..............                                                           [100%]
14 passed, 221 deselected

$ cd cli && uv run python -m pytest -q tests/test_api_contract_parity.py
4 passed
```

`test_api_contract_parity.py` compares the served OpenAPI surface (worker and manager)
with `docs/api-specs/openapi/the-loop.v1.yaml`, so it is green only because the contract
now names `POST /api/v1/pull-requests/ready` (`markPullRequestReady`).

## T7: the full suite and the hooks

```text
$ cd cli && uv run python -m pytest -q
5391 passed, 1 skipped in 216.89s (0:03:36)

$ uv run ruff check cli hooks
All checks passed!

$ uv run ruff format --check cli hooks
413 files already formatted

$ uv run pyright cli
0 errors, 0 warnings, 0 informations

$ npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Linting: 1569 file(s)
Summary: 0 error(s)

$ uv run python scripts/validate_config.py
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

## Results

| Activity | Command | Outcome | Evidence |
|---|---|---|---|
| T1 client | `pytest tests/test_ghapi.py -k mark_pull_ready` | pass (red first) | above |
| T2 core | `pytest tests/test_github_ops.py -k 465` | pass (red first) | above |
| T3 abuse | `pytest tests/test_github_ops.py -k abuse_465` | pass (red first) | above |
| T4 CLI | `pytest tests/test_github_verbs_cli.py -k 465` | pass (red first) | above |
| T5 integration | `pytest tests/test_github_verbs_integration.py -k 465` | pass (red first) | above |
| T6 contract / MCP | `test_api_contract_parity.py`, `test_mcp_integration.py` | pass (MCP red first) | above |
| T7 regression | full suite + hooks | pass | above |
| T8 security | review | pass | [`security-review.md`](security-review.md) |
| T9 | — | n/a | no UI, no stored data |
