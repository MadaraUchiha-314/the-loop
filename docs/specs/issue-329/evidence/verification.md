# Verification — issue-329

> The testing plan executed (`testing-plan.md`, rows T1, T2, T3, T9, T11, T13). Commands
> run from the repository root at the head of `claude/github-issue-329-fide3i`. Every
> login, ref and path in the tests is a fixture (`octocat`, `stranger`, `octo/repo`,
> `loop-lab`, a pytest tmp path). Nothing here needed redaction.

## Red → green

The new tests were written first. With the source files stashed back to `cab21a6`
(13.6.0) and only the tests in place, the twenty new service tests fail and ten
pre-existing ones in the same selection still pass:

```text
git stash push -- cli/the_loop
uv run --project cli python -m pytest -q cli/tests/test_poller.py cli/tests/test_poller_integration.py \
  cli/tests/test_webhook_routing_integration.py cli/tests/test_routing.py \
  -k "ended or reconciled or closer or stamp or untracked or tracked or reopen"
FAILED cli/tests/test_poller.py::test_provider_closure_carries_the_closer
FAILED cli/tests/test_poller.py::test_provider_closure_event_names_the_closer_as_sender
FAILED cli/tests/test_poller.py::test_a_closed_session_is_asked_once_and_not_again_once_stamped
FAILED cli/tests/test_poller.py::test_a_paused_sessions_closed_item_is_reconciled
FAILED cli/tests/test_poller.py::test_a_record_without_a_session_is_reconciled[control]
FAILED cli/tests/test_poller.py::test_a_record_without_a_session_is_reconciled[graph]
FAILED cli/tests/test_poller.py::test_a_record_without_a_session_is_reconciled[collaborators]
FAILED cli/tests/test_poller.py::test_a_listed_item_clears_its_ended_stamp
FAILED cli/tests/test_poller_integration.py::test_a_paused_sessions_closed_item_is_detected_and_stamped
FAILED cli/tests/test_poller_integration.py::test_a_polled_closure_by_an_authorized_closer_releases_the_item
FAILED cli/tests/test_poller_integration.py::test_a_polled_closure_by_an_unlisted_closer_is_deferred
FAILED cli/tests/test_webhook_routing_integration.py::test_a_closed_issue_with_no_session_is_stamped_ended
FAILED cli/tests/test_webhook_routing_integration.py::test_reopening_an_issue_clears_the_stamp
FAILED cli/tests/test_routing.py::test_an_issue_close_stamps_the_work_item_ended
FAILED cli/tests/test_routing.py::test_a_close_with_no_session_still_stamps_a_tracked_record
FAILED cli/tests/test_routing.py::test_a_close_for_an_untracked_ref_creates_no_record
FAILED cli/tests/test_routing.py::test_a_closed_session_record_counts_as_tracked
FAILED cli/tests/test_routing.py::test_a_pr_merge_stamps_the_prs_own_record_and_not_the_linked_issue
FAILED cli/tests/test_routing.py::test_a_reopen_clears_the_ended_stamp
FAILED cli/tests/test_routing.py::test_the_stamp_is_logged_as_work_item_ended
20 failed, 10 passed, 398 deselected in 2.09s
git stash pop
```

The task-1 tests (`test_workitem.py`, `test_control.py`, `test_reset.py`) were run red the
same way before the store changed — `4 failed, 1 passed, 98 deselected` — and the seven
dashboard tests were red against the unchanged `model.ts` / `grouping.ts` / `fixture.ts`
(`Tests 7 failed | 212 passed (219)`) because the edit script that carried those three
files stopped before reaching them; the tests then went green once the edits were applied.

| Task | Red (before the change) | Green |
|------|-------------------------|-------|
| 1 the fact | `ENDED` absent from `SECTIONS`; no `record_ended` / `ended` / `clear_ended`; reset leaves the section; `work_item.*` unknown to the catalog | `test_a_record_with_only_ended_is_kept_and_indexed`, `test_record_ended_and_clear_ended`, `test_a_malformed_ended_reads_as_not_ended`, `test_reset_clears_the_ended_section`; `test_eventlog.py::test_every_emitted_event_type_is_documented` |
| 2 the writer | the close path clears `control` / `collaborators` and nothing else; a session-less close returns with a debug line; `reopened` is an ordinary event | the eight `test_routing.py` tests above; the two webhook scenarios |
| 3 more closures | only active sessions reconciled; `Closure` has no `actor`; the polled event has no `sender` | the ten `test_poller.py` tests above (one rewritten); the three poll scenarios |
| 4 the readers | `attention` reports the stale question and arming; the join has no `ended`, the gated record lands in `needs-you` | `test_an_ended_item_asks_for_no_attention`; `model.test.ts › an ended work item (issue-329)` ×4; `grouping.test.ts › sidebarGroup for an ended item` ×3 |
| 5 docs | — | `make lint` (markdownlint over every `*.md`), `test_docs_parity.py` |

Existing assertions changed: one — `test_an_already_closed_session_is_not_reconciled_again`
pinned the rule that was the gap and is now `test_a_closed_session_is_asked_once_and_not_again_once_stamped`.
Three existing test files gained a tmp `portable_dir` (`test_routing.py`'s factory,
`test_workspace.py`'s two builders): a close now writes a record, and `RoutingConfig`'s
default portable directory is the checkout's own.

## Rows T1, T2, T3, T9, T11

```text
== T1
uv run --project cli python -m pytest -q cli/tests/test_workitem.py cli/tests/test_portable_index.py cli/tests/test_control.py cli/tests/test_routing.py cli/tests/test_poller.py cli/tests/test_reset.py cli/tests/test_core_attention.py
496 passed in 4.06s
== T2
cd ui && bun run test
 Test Files  16 passed (16)
      Tests  219 passed (219)
== T3
uv run --project cli python -m pytest -q cli/tests/test_webhook_routing_integration.py cli/tests/test_poller_integration.py
63 passed in 21.47s
== T9
uv run --project cli python -m pytest -q cli/tests/test_routing.py cli/tests/test_poller.py cli/tests/test_core_attention.py -k "ended or reopened or closer or untracked"
11 passed, 364 deselected in 0.20s
== T11
uv run --project cli python -m pytest -q cli/tests/test_eventlog.py cli/tests/test_docs_parity.py
19 passed in 0.67s
```

## Row T13 — `make check` and the dashboard's three commands

```text
make check
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Summary: 0 error(s)
uv run ruff format --check cli hooks
281 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
uv run --project cli python -m pytest -q cli
3165 passed, 1 skipped in 146.75s (0:02:26)

cd ui
bun run lint     → oxlint --type-aware, clean
bun run test     → Test Files 16 passed (16) · Tests 219 passed (219)
bun run build    → tsc --noEmit && vite build · ✓ built in 1.38s
```

## Security

See [`security-review.md`](security-review.md) — abuse cases A1–A6, each closed by a
named test; no human sign-off at tier 3.
