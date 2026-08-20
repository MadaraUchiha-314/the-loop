# Red run — the tests that motivate the change (issue-274)

Captured before any production code changed: at this point only `cli/tests/*` and the
spec chain exist, so every failure below is the reported bug.

## Command

```console
$ uv run --project cli python -m pytest -q \
    cli/tests/test_core_sessions.py cli/tests/test_routing.py \
    cli/tests/test_webhook_routing_integration.py \
    -k "link_pull_request or link_pr or spec_pr"
```

## Output

```text
=========================== short test summary info ============================
FAILED cli/tests/test_core_sessions.py::test_link_pull_request_records_the_pr_and_emits
FAILED cli/tests/test_core_sessions.py::test_link_pull_request_is_idempotent
FAILED cli/tests/test_core_sessions.py::test_link_pull_request_without_a_session_record_writes_nothing
FAILED cli/tests/test_core_sessions.py::test_link_pull_request_refuses_a_work_item_delivering_itself
FAILED cli/tests/test_core_sessions.py::test_link_pull_request_resolves_a_number_in_the_work_items_repository[6]
FAILED cli/tests/test_core_sessions.py::test_link_pull_request_resolves_a_number_in_the_work_items_repository[#6]
FAILED cli/tests/test_core_sessions.py::test_link_pull_request_resolves_a_number_in_the_work_items_repository[ 6 ]
FAILED cli/tests/test_core_sessions.py::test_link_pull_request_resolves_a_number_in_the_work_items_repository[github:octo/repo#6]
FAILED cli/tests/test_core_sessions.py::test_link_pull_request_accepts_a_pull_request_in_another_repository
FAILED cli/tests/test_core_sessions.py::test_link_pull_request_refuses_malformed_input[not-a-ref-6]
FAILED cli/tests/test_core_sessions.py::test_link_pull_request_refuses_malformed_input[github:octo/repo#5-not-a-ref]
FAILED cli/tests/test_core_sessions.py::test_link_pull_request_refuses_malformed_input[github:octo/repo#5-0]
FAILED cli/tests/test_core_sessions.py::test_link_pull_request_refuses_malformed_input[github:octo/repo#5--3]
FAILED cli/tests/test_core_sessions.py::test_link_pull_request_refuses_malformed_input[github:octo/repo#5-]
FAILED cli/tests/test_core_sessions.py::test_link_pull_request_refuses_malformed_input[github:octo/repo#5-#]
FAILED cli/tests/test_routing.py::test_sessions_command_link_pr_records_the_binding
FAILED cli/tests/test_routing.py::test_sessions_command_link_pr_reports_a_missing_record_and_a_bad_ref
FAILED cli/tests/test_webhook_routing_integration.py::test_a_review_comment_on_the_loops_own_spec_pr_reaches_the_session_once_recorded
18 failed, 4 passed in 3.00s
```

## What the failures say

All eighteen fail on the same missing thing — `module 'the_loop.core.sessions' has no
attribute 'link_pull_request'` — which is the defect stated as a test: the-loop has no way
to record a pull request it opened, so the binding the router prefers is never written.

## What the four passes say — and why one of them is the bug

Three are pre-existing registry tests the `-k` filter caught (`link_pull_request` on
`SessionRegistry`). The fourth is this work item's **control**, and it is the reproduction:

```text
cli/tests/test_webhook_routing_integration.py::test_a_review_comment_on_the_loops_own_spec_pr_is_lost_without_the_binding PASSED
```

It asserts the broken behaviour — a review comment on a the-loop-authored spec pull request
(no closing reference, a `loop/<id>-…` head branch, a body that only mentions the issue)
reaches **no session at all**: not the work item's, and not a spawned one. It passes before
the fix and after it, because the fix does not change what happens to an *unrecorded* pull
request. What changes is that the-loop now records the ones it opens — which its twin,
`…_reaches_the_session_once_recorded`, is the failing half of.

## Where the tests live

| Layer | File |
|---|---|
| Unit — the operation and every acceptance criterion of R1 | `cli/tests/test_core_sessions.py` |
| CLI — `sessions link-pr` parses, routes and renders | `cli/tests/test_routing.py` |
| Integration — the reproduction, both halves, Gherkin-documented | `cli/tests/test_webhook_routing_integration.py` |
