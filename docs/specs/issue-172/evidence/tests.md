# Evidence — test runs

> Work item: [issue #172](https://github.com/MadaraUchiha-314/the-loop/issues/172) ·
> Testing plan rows **T1, T2, T2b, T8, T10** · captured 2026-08-07.
>
> Nothing here is redacted, and nothing needed to be: the outputs are pytest summaries and
> test names. No network call, no `gh` invocation, no secret store is involved in any row.

## Full suite

```console
$ uv run --directory cli pytest -q
1404 passed, 1 skipped in 42.59s
```

The one skip is pre-existing and unrelated; the baseline before this change was
`1379 passed, 1 skipped`. **25 tests added**, none removed, and one existing test changed —
the fixture line noted under T2.

## T1 — the store, the resolver, the router helper

```console
$ uv run --directory cli pytest tests/test_routing.py -q
103 passed in 1.45s
```

New in this file:

```text
test_registry_link_binds_a_ref_to_another_items_session
test_registry_link_is_idempotent_and_keeps_created_at
test_registry_refuses_to_bind_a_ref_to_itself
test_registry_resolve_link_does_not_follow_a_chain
test_registry_treats_an_unparseable_binding_as_absent
test_registry_binding_file_names_cannot_escape_the_directory
test_registry_bindings_are_invisible_to_the_session_listing
test_registry_links_to_and_unlink
test_registry_binding_survives_closing_the_session_it_names
test_pr_work_item_names_the_ref_extraction_emits_last
test_pr_work_item_is_none_for_events_that_concern_no_pull_request
test_pr_work_item_carries_the_host_off_the_payload
test_delivery_status_follows_a_binding
```

Three are worth naming for what they pin rather than what they assert:

- `test_registry_link_binds_a_ref_to_another_items_session` reads the record back through a
  **fresh** `SessionRegistry` instance. That is R1.4 — "survives a restart" — expressed as
  the filesystem fact it actually is, rather than by restarting a daemon.
- `test_pr_work_item_names_the_ref_extraction_emits_last` asserts `pr_work_item(...)` equals
  `extract_work_items(...)[-1]` on both PR-shaped events. The two functions could drift into
  writing a binding under a ref routing never produces; this makes that a red build.
- `test_delivery_status_follows_a_binding` is one of the two self-review findings (below).

## T2 — the ticket's reproduction, as an integration test

```console
$ uv run --directory cli pytest tests/test_webhook_routing_integration.py -q
22 passed in 11.36s
```

New in this file, each with a Gherkin docstring and a `Requirement:` link:

```text
test_pr_event_still_reaches_the_linked_issues_session_after_the_link_is_removed
test_a_binding_does_not_suppress_a_session_the_linkage_still_finds
test_spawning_for_a_linked_issue_records_the_binding
test_a_stop_on_an_unlinked_pr_stops_the_bound_session
test_a_pr_close_matched_through_a_binding_leaves_the_session_open
test_a_pr_with_its_own_session_is_still_auto_closed
```

One fixture detail surfaced while writing these and is recorded because it is a real property
of the code: `test_a_stop_on_an_unlinked_pr_stops_the_bound_session` has to pass
`authorized_users` to the **dispatcher's** config as well as the router's. That is
issue-106's deliberate asymmetry — the control path re-checks authorization more strictly
than the ingress guard — and the first draft failed with
`refusing the stop command on github:octo/repo#16: unauthorized-actor` until the fixture said
so.

## T2b — the poll path (added during self-review)

```console
$ uv run --directory cli pytest tests/test_poller.py -q
107 passed in 0.26s
```

Self-review round 1 swept every remaining `find_by_work_item` call site rather than only the
ones the design named, and found the same defect twice more on the poll ingress. Both are now
covered, and both were regressions the first draft would have shipped:

| Finding | Consequence before the fix | Test |
|---|---|---|
| `Dispatcher.delivery_status` asked the registry about the **routed** refs, but a binding-resolved delivery records its id on the **bound** session's record | a successful delivery reports `unhandled`, so the poller re-forwards the same comment until `maxRetries` is spent, then logs a terminal failure | `test_delivery_status_follows_a_binding` (in T1's file) |
| `Poller._process_item`'s `has_session` had the same shape | a PR whose linkage is gone is treated as **first sight**: its entire existing thread is baselined as read, and a spawn is armed against the PR while the issue's session runs | `test_a_stored_binding_suppresses_presence_when_the_linkage_is_gone` |

The fix for both was to move the resolution onto the registry as `session_for()` — the
question both ingresses ask — instead of leaving it a private dispatcher helper the poller
would have had to reach through the dispatcher for.

## T2/T2b (negative) — the regression tests against the un-fixed code

Both halves of the fix were reverted in-process by a pytest plugin that rebinds
`SessionRegistry.session_for` to the bare `find_by_work_item` and `_record_pr_binding` to a
no-op. This is the check that the checks check something.

```console
$ PYTHONPATH=… uv run pytest tests/test_webhook_routing_integration.py tests/test_routing.py \
    tests/test_poller.py -q -p prefix_plugin \
    -k "binding or linked or bound or auto_closed or delivery_status"
FAILED …::test_pr_event_still_reaches_the_linked_issues_session_after_the_link_is_removed
FAILED …::test_a_binding_does_not_suppress_a_session_the_linkage_still_finds
FAILED …::test_spawning_for_a_linked_issue_records_the_binding
FAILED …::test_a_stop_on_an_unlinked_pr_stops_the_bound_session
FAILED …::test_delivery_status_follows_a_binding
FAILED …::test_a_stored_binding_suppresses_presence_when_the_linkage_is_gone
6 failed, 16 passed, 210 deselected in 13.72s
```

The poller failure prints the damage directly — the extra event is a spawn armed against the
PR:

```text
E  Left contains one more item: RoutedEvent(event='issues', action='labeled',
   delivery_id='presence-github:octo/repo#42',
   work_items=[WorkItemRef(provider='github', owner='octo', repo='repo', number=42, …)],
   labeled=True)
```

The 16 that still pass include both close scenarios and the pre-existing linked-issue tests —
correctly, because issue-101's and issue-93's behaviour is what this work item must **not**
change.

**Only the resolver reverted**, with the record still written — which isolates the failure
the ticket actually reports:

```console
$ PYTHONPATH=… uv run pytest tests/test_webhook_routing_integration.py -p prefix_resolver \
    -k "after_the_link_is_removed"
>       assert wait_until(lambda: len(tmux.delivers) == 2)
E       assert False
1 failed, 21 deselected in 5.56s
```

The second PR event is never delivered. The binding is on disk and nothing reads it — which
is precisely the state the un-fixed the-loop is in, one file short.

## T8 — the abuse cases

Run as part of T1. Four cases, one per boundary named in `design.md` § Security design:

| Case | Test |
|---|---|
| a hand-edited `sessionRef` holding `../../etc/passwd` reads as **no binding**, and logs no warning | `test_registry_treats_an_unparseable_binding_as_absent` |
| a file name cannot escape the registry directory — the slug sanitiser has no separators | `test_registry_binding_file_names_cannot_escape_the_directory` |
| a self-binding is refused, and no file is written | `test_registry_refuses_to_bind_a_ref_to_itself` |
| a binding whose target is itself bound is **not** followed | `test_registry_resolve_link_does_not_follow_a_chain` |

## T10 — reset, and the state classification

```console
$ uv run --directory cli pytest tests/test_reset.py tests/test_state_portability.py -q
36 passed in 0.12s
```

New:

```text
test_reset_removes_bindings_in_both_directions
test_reset_removes_a_prs_own_binding
test_a_dry_run_reports_the_binding_without_removing_it
test_work_items_with_state_reaches_a_pr_whose_only_state_is_a_binding
```

`test_state_portability.py` needed **no** new test: S1 already requires every `StateLayout`
path to be classified, and S3 already requires `docs/cli/state.md` to classify it the same
way. Adding the `GENERATED_PATHS` entry before the documentation row made S3 fail, naming the
missing row — the assertion doing its job on this very change:

```console
E  AssertionError: session binding (<root>/local/<slug>.link.json) is missing from the
   classification table in docs/cli/state.md
```

## Migration — the no-binding case

Every one of the 1379 pre-existing tests runs against a registry that contains no link
record, and every one of them passes unchanged. That is the upgrade assertion: an
installation that has never routed a PR event behaves identically, and the first event that
routes writes the first record.
