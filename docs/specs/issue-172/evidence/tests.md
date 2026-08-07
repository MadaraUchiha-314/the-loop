# Evidence — test runs

> Work item: [issue #172](https://github.com/MadaraUchiha-314/the-loop/issues/172) ·
> Testing plan rows **T1, T2, T2b, T8, T10** · captured 2026-08-07, after the
> owner-review rebuild to the `pullRequests[]` endpoint model. (The first capture, for
> the link-record version this PR initially carried, is in this file's git history.)
>
> Nothing here is redacted, and nothing needed to be: the outputs are pytest summaries
> and test names. No network call, no `gh` invocation, no secret store is involved.

## Full suite

```console
$ uv run --directory cli pytest -q
1403 passed, 1 skipped in 49.05s
```

The one skip is pre-existing and unrelated; the baseline before this work item was
`1379 passed, 1 skipped`.

## T1 — the store and the resolver

```console
$ uv run --directory cli pytest tests/test_routing.py -q
106 passed in 1.09s
```

New in this file:

```text
test_link_pull_request_records_the_pr_on_the_work_items_record
test_link_pull_request_is_idempotent
test_link_pull_request_refuses_the_work_item_itself
test_record_owning_resolves_a_pr_to_its_work_items_record
test_session_for_prefers_the_prs_own_endpoint
test_a_closed_endpoint_falls_back_to_the_work_items_session
test_close_endpoint_leaves_the_record_live
test_touch_records_deliveries_per_endpoint
test_an_unreadable_pull_request_entry_does_not_take_the_record_down
test_a_nested_pull_request_tree_is_flattened_on_read
test_endpoints_survive_closing_and_reopening_the_record
test_pr_work_item_names_the_ref_extraction_emits_last
test_pr_work_item_is_none_for_events_that_concern_no_pull_request
test_pr_work_item_carries_the_host_off_the_payload
test_delivery_status_resolves_a_prs_endpoint
test_dispatcher_still_routes_pr_events_that_are_not_close
test_dispatcher_delivers_pr_events_into_the_work_items_session_when_collapsed
```

Three pin properties rather than behaviours:

- `test_link_pull_request_records_the_pr_on_the_work_items_record` asserts the registry
  directory holds **exactly one file** — the owner's "single session file for one
  work-item" — and reads it back through a fresh `SessionRegistry` (the restart property
  as a filesystem fact).
- `test_pr_work_item_names_the_ref_extraction_emits_last` asserts the ref a PR is
  recorded under equals `extract_work_items(...)[-1]` on both PR-shaped events, so
  recording and routing cannot drift.
- `test_touch_records_deliveries_per_endpoint` pins that dedup does not leak between a
  work item's conversations — the property that makes several sessions per work item
  safe against redelivery.

## T2 — the ticket's reproduction, as an integration test

```console
$ uv run --directory cli pytest tests/test_webhook_routing_integration.py -q
22 passed in 11.52s
```

The issue-172 scenarios, each with a Gherkin docstring and a `Requirement:` link:

```text
test_pr_comment_reaches_the_linked_issues_work_item
test_pr_event_still_reaches_its_work_item_after_the_link_is_removed
test_a_recorded_pr_does_not_suppress_a_work_item_the_linkage_still_finds
test_spawning_for_a_linked_issue_records_the_binding
test_a_stop_on_an_unlinked_pr_stops_the_bound_session
test_a_pr_close_matched_through_a_binding_leaves_the_session_open
test_a_pr_with_its_own_session_is_still_auto_closed
```

The central one drives two signed POSTs: the first (with `Closes #15`) records PR 16 on
issue 15's record and **spawns the PR's own session**; the second (linkage edited out) is
**delivered into that session**, with no duplicate spawn and no record ever minted for
the PR. The close scenario now also asserts the PR's endpoint is closed while the work
item's session stays live — issue-101's rule expressed in the model.

Two fixture details recorded because they are real properties of the code:
`test_a_stop_on_an_unlinked_pr_stops_the_bound_session` must pass `authorized_users` to
the **dispatcher's** config as well as the router's (issue-106's deliberate stricter
re-check), and the R2.3 both-records scenario runs in collapsed mode
(`sessionPerPr: false`) so its both-deliver assertion stays sharp — under per-PR sessions
the two records' endpoints would contend for the PR's one `loop-<slug>` tmux name
(decision-064 § Known edge).

## T2b — the poll path

```console
$ uv run --directory cli pytest tests/test_poller.py -q
107 passed in 0.24s
```

The two poll-path regressions found in self-review of the first draft remain covered in
the rebuilt model:

| Case | Consequence before the fix | Test |
|---|---|---|
| retry accounting asks about the PR's ref, but the delivery id lives on the PR's endpoint | a successful delivery reports `unhandled`; the poller re-forwards the same comment until `maxRetries` is spent | `test_delivery_status_resolves_a_prs_endpoint` |
| first-sight detection asks about the PR's ref | a running PR is treated as first sight: its whole thread is baselined as read and a spawn armed against it | `test_a_recorded_pr_suppresses_presence_when_the_linkage_is_gone` |

## T2/T2b (negative) — the regression tests against the un-fixed code

A pytest plugin rebinds `SessionRegistry.record_owning` to the bare `find_by_work_item`
and `_record_pr_binding` to a no-op — the pre-issue-172 behaviour, everything else
identical:

```console
$ PYTHONPATH=… uv run pytest tests/test_webhook_routing_integration.py tests/test_poller.py \
    -q -p prefix_plugin -k "…issue-172 scenarios…"
FAILED …::test_pr_comment_reaches_the_linked_issues_work_item
FAILED …::test_pr_event_still_reaches_its_work_item_after_the_link_is_removed
FAILED …::test_a_recorded_pr_does_not_suppress_a_work_item_the_linkage_still_finds
FAILED …::test_spawning_for_a_linked_issue_records_the_binding
FAILED …::test_a_stop_on_an_unlinked_pr_stops_the_bound_session
FAILED …::test_a_pr_close_matched_through_a_binding_leaves_the_session_open
FAILED …::test_a_recorded_pr_suppresses_presence_when_the_linkage_is_gone
7 failed, 122 deselected in 28.22s
```

All seven fail, as they must — the checks check something.

## T8 — the abuse cases

Run as part of T1, one per boundary in `design.md` § Security design:

| Case | Test |
|---|---|
| a hand-edited entry (`../../etc/passwd` as a ref) is skipped **per entry**; the work item's own session survives | `test_an_unreadable_pull_request_entry_does_not_take_the_record_down` |
| a nested `pullRequests` tree is flattened on read — no structure to walk | `test_a_nested_pull_request_tree_is_flattened_on_read` |
| a work item cannot be recorded as its own PR | `test_link_pull_request_refuses_the_work_item_itself` |
| a closed/unspawnable endpoint falls back to the record — an event never reaches nowhere | `test_a_closed_endpoint_falls_back_to_the_work_items_session` |

## T10 — reset, migration, and the state classification

```console
$ uv run --directory cli pytest tests/test_reset.py tests/test_state_portability.py -q
32 passed in 0.13s
```

The rebuild made this row **smaller**: the PR entries live inside `local/<slug>.json`, so
there is no new generated path to classify, no new `.gitignore` line, and no new reset
piece — deleting the record takes its PRs with it. `test_state_portability.py` passes
unmodified, which is the assertion that nothing about the on-disk taxonomy changed.

Migration is the absent-key case: every record written before issue-172 has no
`pullRequests` key, parses to an empty list, and round-trips byte-identically
(`to_dict` omits the key when the list is empty). Every pre-existing test runs against
such records and passes unchanged.
