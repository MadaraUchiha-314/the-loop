# Evidence — the green run

Every activity in the testing plan, executed. All counts are from this branch.

## T1 — unit, the dispatcher seam

```sh
uv run --project cli python -m pytest cli/tests/test_routing.py -q -p no:randomly
```

```text
111 passed in 1.92s
```

Four of those rows are new or rewritten:
`test_dispatcher_still_routes_pr_events_that_are_not_close` (R1.1, R1.3),
`test_a_same_repo_pr_never_gets_a_session_even_once_it_has_a_record` (R1.2),
`test_a_cross_repo_pr_without_a_workspace_is_declined_not_collided` (R2.2–R2.4) and
`test_an_endpoint_checkout_that_lands_on_the_records_tree_is_refused` (R2.2), which
drives the `shared-worktree` guard through the real spawn seam and asserts the
workspace branch — not the no-workspace one — is what ran.

## T4 — end-to-end against a real `git` workspace

```sh
uv run --project cli python -m pytest cli/tests/test_workspace.py -q -p no:randomly
```

```text
35 passed in 1.60s
```

`test_a_cross_repo_pr_endpoint_spawns_in_its_own_checkout` is the one that proves R2.1
against real bare repositories: the endpoint's spawn `cwd` is
`…/.worktrees/github.com/octo/other/github-octo-other-16` — the *other* repository's tree,
keyed on the pull request's own slug — and it asserts explicitly that this is **not** the
record's `…/octo/repo/github-octo-repo-15`.

## T2 — integration, HTTP delivery through the receiver

```sh
uv run --project cli python -m pytest cli/tests/test_webhook_routing_integration.py -q -p no:randomly
```

```text
22 passed in 11.24s
```

## T8 / T10 — the abuse-case and read-forward selections

```sh
uv run --project cli python -m pytest cli/tests -q -p no:randomly -k cross_repo
uv run --project cli python -m pytest cli/tests -q -p no:randomly -k even_once_it_has_a_record
```

```text
7 passed, 2165 deselected in 2.30s
1 passed, 2171 deselected in 1.95s
```

## T12 — the whole CLI suite

```sh
uv run --project cli python -m pytest cli/tests -q -p no:randomly
```

```text
2172 passed, 1 skipped in 110.92s (0:01:50)
```

No pre-existing failures were observed on this run. (Issue
[#251](https://github.com/MadaraUchiha-314/the-loop/issues/251) tracks load-flaky tests in
this suite; none of them failed here.)

The event-catalogue drift check — the one that would have caught
`session.pr_session_declined` being emitted without being documented — is inside that run:

```sh
uv run --project cli python -m pytest cli/tests/test_eventlog.py -q -p no:randomly
```

```text
14 passed in 0.49s
```
