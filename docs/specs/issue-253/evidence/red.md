# Evidence — the red run

Every test guarding this fix, run with the dispatcher change reverted
(`git stash push cli/the_loop/webhook/dispatcher.py`) and the tests in place. Six fail; each
failure is the defect itself, stated as an assertion.

## Command

```sh
git stash push cli/the_loop/webhook/dispatcher.py
uv run --project cli python -m pytest \
  cli/tests/test_routing.py::test_dispatcher_still_routes_pr_events_that_are_not_close \
  cli/tests/test_routing.py::test_a_same_repo_pr_never_gets_a_session_even_once_it_has_a_record \
  cli/tests/test_routing.py::test_a_cross_repo_pr_without_a_workspace_is_declined_not_collided \
  cli/tests/test_workspace.py::test_a_cross_repo_pr_endpoint_spawns_in_its_own_checkout \
  cli/tests/test_webhook_routing_integration.py::test_pr_comment_reaches_the_linked_issues_work_item \
  cli/tests/test_webhook_routing_integration.py::test_pr_event_still_reaches_its_work_item_after_the_link_is_removed \
  -q -p no:randomly
```

## Result

```text
FAILED cli/tests/test_routing.py::test_dispatcher_still_routes_pr_events_that_are_not_close
FAILED cli/tests/test_routing.py::test_a_same_repo_pr_never_gets_a_session_even_once_it_has_a_record
FAILED cli/tests/test_routing.py::test_a_cross_repo_pr_without_a_workspace_is_declined_not_collided
FAILED cli/tests/test_workspace.py::test_a_cross_repo_pr_endpoint_spawns_in_its_own_checkout
FAILED cli/tests/test_webhook_routing_integration.py::test_pr_comment_reaches_the_linked_issues_work_item
FAILED cli/tests/test_webhook_routing_integration.py::test_pr_event_still_reaches_its_work_item_after_the_link_is_removed
6 failed in 21.55s
```

## What each failure says

**R1.1 / R1.3 — the ownership rule.** The delivery never arrives, because a session is
spawned for the pull request instead:

```text
assert False
 +  where False = wait_until(<test_dispatcher_still_routes_pr_events_that_are_not_close.<locals>.<lambda>>)
```

**R1.2 — a pre-existing endpoint keeps being fed.** The event goes to the leftover
conversation rather than the work item's:

```text
AssertionError: assert 'github:octo/repo#16' == 'github:octo/repo#15'
  - github:octo/repo#15
  + github:octo/repo#16
```

**R2.2 — a cross-repository pull request with no workspace collides instead of declining.**
The delivery never arrives, for the same reason: it spawned.

**R2.1 — the endpoint's checkout is the work item's.** This is the root cause printed
verbatim: the spawn's `cwd` is `octo/repo`'s worktree for work item 15, where the pull
request's own would be `octo/other`'s for pull request 16.

```text
AssertionError: assert
  PosixPath('…/root/.worktrees/github.com/octo/repo/github-octo-repo-15')
       == PosixPath('…/root/.worktrees/github.com/octo/other/github-octo-other-16')
```

**R1.1 / R1.4 at the webhook seam.** Both integration scenarios fail on the same missing
delivery — end to end from an HTTP delivery, the event still lands in a second session.
