---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#370"
---

<!-- Authored per the the-loop:writing skill. -->

# Final validation: a pull request is tracked because the-loop recorded it

> The `evidence` node's proof, mapped onto `requirements.md`'s acceptance criteria.

## Gates

```text
$ make lint format-check typecheck validate
All checks passed!                      (ruff check cli hooks)
303 files already formatted             (ruff format --check cli hooks)
Summary: 0 error(s)                     (markdownlint-cli2, 1111 files)
0 errors, 0 warnings, 0 informations    (pyright cli)
VALID × 6                               (scripts/validate_config.py)

$ uv run --project cli python -m pytest -q cli
3749 passed, 1 skipped in 181.94s (0:03:01)
```

Baseline on `main` (this branch stashed, same command): **3736 passed, 1 skipped**. The
net +13 is the removal and rewrite of existing tests alongside the additions: 20 new tests
in `test_harness_link_pr.py`, 5 in `test_graphlink.py`, 5 in `test_graph_state.py`, 3 in
`test_instance.py`, 2 in `test_graph_review.py`, and one each in `test_poller.py` and
`test_poller_integration.py`, against the `linked-pulls` and inferred-linkage tests the
change retired.

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| **AC1** a PR linked only by inference keeps a record of its own; the issue's record gains no `pullRequests` entry and the index lists none | T1 — a labelled PR whose provider refs name issue 15 is ledgered under itself; `store.section(issue, PULL_REQUESTS) is None`, `owner_of(pr) is None`, and issue 15 gets no record file at all | `test_poller.py::test_an_inferred_linkage_no_longer_files_a_pull_request_under_a_work_item` |
| **AC2** the same PR, with a recorded binding, is ledgered under the work item as before | T2 — the registry binding `link_pull_request` writes is the owner; one record, one index entry | `test_poller.py::test_a_labelled_pull_request_is_ledgered_under_the_work_item_it_delivers` |
| **AC3** a comment on that PR is still delivered to the work item's session | T3 — the real provider and the real dispatcher, end to end: the comment lands in issue 15's tmux session while the same run asserts the tracking stayed empty | `test_poller_integration.py::test_an_inferred_pull_request_is_delivered_but_never_tracked` |
| **AC4** an event adds no row to `work-item-state.json`; `link-pr` does; a v1 `"event"` row survives | T4/T5/T6 — `on_pr_linked` records `linkedBy: "session"` and the dispatcher no longer calls it; a hand-written `"event"` row loads and re-saves unchanged; `set_pr_state` still mutates an existing row and creates none | `test_graph_state.py`, `test_core_sessions.py` (link-pr suite), `test_webhook_routing_integration.py` |
| **AC5** the review brief lists the recorded PRs; no `linked-pulls` op exists | T7/T8 — `OPERATIONS` has no `linked-pulls` and both transports raise `OperationUnsupported`; the brief pre-fills from `pullRequests[]` then `pr-loops/`, deduped, ignores the fake provider's `pulls`, and asserts the op was never called | `test_graph_integrations.py`, `test_graph_review.py` (3 tests) |
| **AC6** the hook links a created PR and is a silent no-op on every degraded input | T9/T10/T11/T13/T15 — 20 tests over the documented stdin contract: the three work-item resolutions, the cross-repo full ref, the enterprise host, and eight degraded inputs each asserting `(0, "")` and zero subprocesses | `test_harness_link_pr.py` |
| **AC8** a PR armed as its own work item is in its own `pullRequests[]` with `self: true` and no `stateDir`; an issue-armed one is not; the self ref is still refused without the marker; a hand-written `stateDir` on a marked row is dropped | T18/T19 — four state-level tests and five graphlink tests, including the three ways "is this a pull request?" must answer *no* (an issue, a *different* PR, no event at all) | `test_graph_state.py`, `test_graphlink.py` |
| **AC7** a tmux spawn for a work item carries `-e THE_LOOP_WORK_ITEM=<ref>` | T12 — both env vars on a spawn with a work item and an instance; none on a standing session; an old tmux omits both with one warning naming them and no failed spawn | `test_instance.py` (3 tests) |

## What a reviewer should verify by hand

Nothing in this change needs credentials or the network, and nothing is asserted only by
reading. The one judgement call is the boundary itself — **delivery keeps the inference,
tracking loses it** — which is `design.md` § Overview and
[decision-129](../../decisions/decision-129.md).

The owner ruled on the related question on
[PR #372](https://github.com/MadaraUchiha-314/the-loop/pull/372): the entity the-loop
manages is one work item whatever represents it, so a pull request armed by
`review`/`contribute` is now recorded in its own `pullRequests[]` (R7, C6). That ruling
settled the ontology; it did **not** say to remove the delivery inference, so that reading
stays in `requirements.md` § Out of scope with what it would cost.
