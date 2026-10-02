---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#452"
---

<!-- Authored per the the-loop:writing skill. -->

# Verification (issue-452)

Executed at the `verification` node on 2026-10-02, on this work item's branch
(`claude/github-issue-452-d7mohp`), in the work item's cloud checkout: `uv 0.12.22`,
Python 3.11, no network for the tests. One section per row of `testing-plan.md`. The
summaries are as the runner printed them, from `cli/`.

## Red first (negative control)

The new tests were written before the code. Against the unchanged source (`git stash`
of `cli/the_loop/` only, tests kept):

```text
$ uv run python -m pytest -q tests/test_archive.py
E   ImportError: cannot import name 'archive' from 'the_loop'

$ uv run python -m pytest -q tests/test_archive_dispatch.py
E   ImportError: cannot import name 'archive' from 'the_loop'

$ uv run python -m pytest -q tests/test_archive_integration.py tests/test_poller.py tests/test_ghapi.py
FAILED tests/test_archive_integration.py::test_a_completed_work_item_is_checked_after_normal_cleanup
FAILED tests/test_archive_integration.py::test_the_table_says_archived_and_never_unmet
FAILED tests/test_archive_integration.py::test_graph_status_renders_the_same_archive
FAILED tests/test_archive_integration.py::test_the_daemon_restarts_between_cleanup_and_check
FAILED tests/test_poller.py::test_provider_closure_carries_the_state_reason
FAILED tests/test_poller.py::test_provider_closure_event_puts_the_state_reason_on_the_issue
FAILED tests/test_ghapi.py::test_item_state_reads_the_state_reason
… plus 9 existing poller tests, red only because the updated client double passes
  `state_reason=` to the old `GhItemState`
16 failed, 288 passed
```

The integration scenario reproduces the issue exactly: on the old source `check
github:octo/repo#3 --format json --fail-on block` from the deployment directory printed
`"currentNode": "phase-selection"`, `"ok": false`, `"stateFound": false`. Outcome:
**pass** (red as expected).

## T1 + T2 + T10: unit — the record, the outcome, `check`'s archived branch

```text
$ uv run python -m pytest -q tests/test_archive.py
28 passed
```

The record: a claimed `complete` is `completed` with its exit time; a pointer at
`human-approval`, and a `complete` entered but never claimed, are not; `cleanup` after a
claimed `complete` still is; no state file is no record. The outcome truth table never
yields `completed` without the record's claim. `check`: a ref with a stamp and no state
file is archived with no node findings; a found state file, a bare id, and `--recompute`
over a present spec directory are unchanged; a pre-change stamp (T10) and a malformed
`terminal` read as `detail: unavailable`; no CLI config means no archive. Outcome:
**pass**.

## T3 + T7: unit — the close path

```text
$ uv run python -m pytest -q tests/test_archive_dispatch.py
7 passed
```

The stamp carries the record read while the checkout existed (the test's removal seam
deletes the directory, and the record is still there); `not_planned` on a mid-flight item
is `cancelled`; a completed-reason close of a mid-flight item is `closed-externally`; a
session-less tracked close reads the registry's checkout; a foreign checkout gives
`unknown` and no record; `cleanup` backfills a stamp before the checkout goes, and writes
none for an open item. Outcome: **pass**.

## T4: unit — the poller's `state_reason`

```text
$ uv run python -m pytest -q tests/test_poller.py tests/test_ghapi.py tests/test_poller_integration.py
333 passed
```

Outcome: **pass**.

## T5: integration — the issue's reproduction

```text
$ uv run python -m pytest -q tests/test_archive_integration.py
4 passed
```

A real dispatcher, a real git worktree, `keepCheckoutOnClose: false`, an authorized
closer: the worktree and the session record are gone after the closure. `the-loop check
github:octo/repo#3 --format json --fail-on block` from an unrelated directory exits 0 with
`archived.outcome: completed`, `nodes: []`, `currentNode: complete`, the seven skipped
phases (and not `implementation`), `harness: codex`, the merged pull request and the
evidence file. The table prints `issue-3: ARCHIVED — completed (at complete)` with no
`UNMET`/`BLOCK`; `graph status` prints the same head line. Rebuilding the daemon over the
same state directory leaves the stamp unchanged, spawns nothing, and `check` still
answers. Outcome: **pass**.

## T6: contract

```text
$ uv run python -m pytest -q tests/test_api_contract_parity.py
4 passed
```

Outcome: **pass** (descriptions changed; surface unchanged).

## T11: regression, lint, format, typecheck

```text
$ uv run python -m pytest -q tests/test_cleanup.py tests/test_cleanup_integration.py tests/test_routing.py tests/test_finish_grace.py tests/test_graph_status_resolution.py tests/test_core_graphs.py
288 passed

$ uv run python -m pytest -q
5338 passed, 1 skipped

$ uv run ruff check cli hooks
All checks passed!

$ uv run ruff format --check cli hooks
411 files already formatted

$ uv run pyright cli
0 errors, 0 warnings, 0 informations

$ npx --yes markdownlint-cli2@0.18.1 <the changed markdown>
Summary: 0 error(s)
```

The first full run found one regression: test doubles of the graph link
(`tests/test_finish_grace.py`'s `StubLink`) have no `terminal_record`. The dispatcher now
treats a link without the read as having no record — an embedder's coupling may predate
this change too — and the suite is green. Outcome: **pass**.

## Not run

T8 (live end-to-end against `the-loop-testing`) is not run here: it needs a daemon, a
GitHub token and a second repository. T5 drives the same close path, worktree removal
included, in-process.
