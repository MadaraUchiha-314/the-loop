# Evidence — red run (before the fix)

The tests were written against the pre-fix tree and run there before any production edit
landed. Three captures, because the change has three kinds of seam and each fails
differently on `main`.

## 1. The reproduction, on the ingress the ticket was reported from

The strongest capture: the **real** `GitHubPollProvider` + `Poller` + `Dispatcher`, one
labelled pull request whose head branch is `issue-285-consolidation`, no
`closingIssuesReferences`, and an authorized `the-loop start` comment. Production code from
`main` (`git stash push -u -- cli/the_loop`), with the two injection seams the fix adds
(`Dispatcher(verifier=…)` and the conftest stub) removed from the test harness, so the
failure is **behavioural**, not "the argument does not exist yet".

```text
>       assert tmux.spawns[0][0] == "github:octo/repo#48"
E       AssertionError: assert 'github:octo/repo#285' == 'github:octo/repo#48'
E
E         - github:octo/repo#48
E         ?                  ^
E         + github:octo/repo#285
E         ?                  ^ +

cli/tests/test_poller_integration.py:937: AssertionError
=========================== short test summary info ============================
FAILED cli/tests/test_poller_integration.py::test_a_branch_invented_work_item_never_becomes_the_start_target
1 failed, 1 passed, 20 deselected in 0.74s
```

That is the ticket, in one line: the branch name said `issue-285`, the repository has no
issue 285, and `main` spawns a session for it.

The **1 passed** in the same run is the control:
`test_the_same_pull_request_still_starts_where_the_work_item_is_real` — the same pull
request, the same branch, a work item that does exist — passes on `main` and after the fix.
Nothing changes for a branch-derived ref that is real, which is what R1.2 ("only a 404
drops a ref") means in practice.

## 2. The webhook-shaped integration scenarios

Same treatment, `cli/tests/test_webhook_routing_integration.py`:

```text
=========================== short test summary info ============================
FAILED …::test_a_start_on_a_cross_repo_pr_does_not_spawn_for_an_invented_work_item
FAILED …::test_an_unverifiable_work_item_keeps_its_place_in_the_routing_decision
FAILED …::test_a_running_work_item_is_never_questioned
3 failed, 24 deselected in 16.68s
```

All three fail at `wait_until(len(tmux.spawns) == 1)` / `len(tmux.delivers) == 1` — nothing
was spawned and nothing was delivered. That is the **second** defect these scenarios pin
(R2.6): they drive a *polled* pull-request comment through `Router.route`, and on `main`
`_pr_entity` reads only `payload["issue"]` for an `issue_comment`, so the payload the poller
synthesises over the pull request names **no work item at all**. On that path no
`session.pr_linked` binding was ever written from a comment and no pull-request endpoint was
ever chosen for one.

## 3. The components that did not exist

```text
=== test_linkage.py (the whole module is new) ===
cli/tests/test_linkage.py:13: in <module>
    from the_loop import linkage as linkage_mod
E   ImportError: cannot import name 'linkage' from 'the_loop'
ERROR cli/tests/test_linkage.py
1 error in 0.14s
```

and, for the router/dispatcher/announcer tests, the conftest stub the fix's own hermetic
rule needs:

```text
>       monkeypatch.setattr(dispatcher_mod, "WorkItemVerifier", _NoopVerifier)
E       AttributeError: <module 'the_loop.webhook.dispatcher'> has no attribute 'WorkItemVerifier'
ERROR cli/tests/test_routing.py::test_a_ref_a_closing_keyword_also_names_is_not_branch_derived
ERROR cli/tests/test_routing.py::test_a_work_item_invented_by_a_branch_name_is_dropped_before_anything_acts
…12 errors, cli/tests/test_announce.py …3 errors, cli/tests/test_webhook_routing_integration.py …3 errors
```

Recorded as it happened rather than dressed up: for a component that does not exist yet the
red is an `ImportError`/`AttributeError`, and capture 1 is the run that proves the
**behaviour** was wrong.

## How each capture was produced

```sh
git stash push -u -- cli/the_loop        # production code back to main; tests stay
# captures 1 and 2 additionally removed the two injection seams from the harness
uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py -k "branch_invented or still_starts_where"
uv run --project cli python -m pytest -q cli/tests/test_webhook_routing_integration.py -k "invented or unverifiable or never_questioned"
uv run --project cli python -m pytest -q cli/tests/test_linkage.py
git stash pop
```
