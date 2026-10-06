---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#466"
---

# Verification (issue-466)

Run on 2026-10-06 on branch `claude/github-issue-466-m9kppv`, using uv 0.12.23 (the
repository requires `>=0.12,<0.13`) and Python 3.11. GitHub is
`ghfakes.FakeGitHubClient`. The suite's autouse fixture refuses any real socket.

## T1–T4: red before the fix

Against the pre-fix code, with the new tests in place:

```text
$ uv run pytest -c cli/pyproject.toml cli/tests/test_github_ops.py \
    cli/tests/test_github_verbs_integration.py -q -k 466
>       assert [item.ref for item in poller.list_work_items()] == [
            "github:octo/repo#12",
            "github:octo/repo#23",
        ]
E       AssertionError: assert [] == ['github:octo...octo/repo#23']
FAILED cli/tests/test_github_ops.py::test_issue_466_pr_create_applies_every_auto_execute_label
FAILED cli/tests/test_github_ops.py::test_issue_466_the_default_label_when_the_operator_set_none
FAILED cli/tests/test_github_ops.py::test_issue_466_an_empty_label_list_labels_nothing
FAILED cli/tests/test_github_ops.py::test_issue_466_a_pull_request_that_is_not_linked_is_not_labelled
FAILED cli/tests/test_github_ops.py::test_issue_466_a_refused_label_is_a_note_not_a_failure
FAILED cli/tests/test_github_ops.py::test_issue_466_link_pr_labels_a_newly_linked_pull_request_once
FAILED cli/tests/test_github_ops.py::test_issue_466_link_pr_without_a_session_labels_nothing
FAILED cli/tests/test_github_ops.py::test_issue_466_link_pr_to_an_untrusted_host_links_but_does_not_label
FAILED cli/tests/test_github_ops.py::test_issue_466_discover_labels_each_newly_linked_pull_request
FAILED cli/tests/test_github_verbs_integration.py::test_issue_466_a_linked_pull_request_is_listed_by_a_two_label_poller
10 failed, 102 deselected in 2.71s
```

The integration test fails the same way the issue did. The two-label poller lists
neither linked PR (`[]`), because neither carries `the-loop: rr`.

## T1–T5: green after the fix

```text
$ uv run pytest -c cli/pyproject.toml cli/tests/test_github_ops.py \
    cli/tests/test_github_verbs_integration.py cli/tests/test_github_verbs_cli.py \
    -q -k "466 or discover"
22 passed, 116 deselected in 4.97s
```

T5: the first full-suite run after the fix failed two existing tests in
`test_github_verbs_cli.py`. Both asserted that the discovery lookup was the **last**
GitHub call, and `add_labels` now follows it. The tests now pick the
`open_pulls_for_head` call by name, and one also asserts the new `labelled …` line.

## T6: full suite and hooks

```text
$ uv run pre-commit run --all-files
ruff (lint + autofix)....................................................Passed
ruff (format)............................................................Passed
pyright (type check cli).................................................Passed
pytest (cli unit tests)..................................................Passed
markdownlint (all markdown, incl. docs)..................................Passed
validate .the-loop config against schema.................................Passed
```

## Live check (after merge)

The next PR the-loop opens on an instance configured with two labels should carry both,
and a `work_item.pr_labelled` line should appear in `.the-loop/logs/events.jsonl`. yaah#23
itself was linked before the fix and needs the diagnosis' workaround: add `the-loop: rr`
by hand.
