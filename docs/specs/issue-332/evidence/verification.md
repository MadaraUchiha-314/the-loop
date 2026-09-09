# Verification — issue-332

> The testing plan executed (`testing-plan.md`, rows T1, T3, T9, T11, T13). Commands
> run from the repository root at the head of `claude/github-issue-332-z3xktv`. Every
> login, ref and path in the tests is a fixture (`octocat`, `nobody`, `octo/repo`, a
> pytest tmp path). Nothing here needed redaction.

## Red → green

The new tests were written first. With `cli/the_loop` stashed back to `161ba52`
(13.7.1) and only the tests in place, the fourteen new tests in the selection fail and
nine pre-existing or old-code-compatible ones pass (the `absent_since` unit test is
outside this selection; it fails the same way, `AttributeError`, and is in the T1
selection below):

```text
git stash push -- cli/the_loop
uv run --project cli python -m pytest -q cli/tests/test_poller.py cli/tests/test_poller_integration.py \
  -k "ledger or poll_only or closure_check"
FAILED cli/tests/test_poller.py::test_poll_state_note_closure_check_writes_through
FAILED cli/tests/test_poller.py::test_a_closed_ledger_only_item_is_forgotten_and_never_asked_again
FAILED cli/tests/test_poller.py::test_a_poll_only_record_seen_this_window_is_not_asked
FAILED cli/tests/test_poller.py::test_a_poll_only_record_checked_this_window_is_not_asked
FAILED cli/tests/test_poller.py::test_a_poll_only_record_with_an_unparsable_timestamp_is_due
FAILED cli/tests/test_poller.py::test_a_listed_poll_only_record_is_not_asked
FAILED cli/tests/test_poller.py::test_a_stamped_poll_only_record_is_not_asked
FAILED cli/tests/test_poller.py::test_a_poll_only_record_beside_a_session_record_is_tracked_not_ledger_only
FAILED cli/tests/test_poller.py::test_a_still_open_ledger_only_item_is_dated_not_closed
FAILED cli/tests/test_poller.py::test_an_unanswerable_ledger_only_item_is_dated_not_retried_next_cycle
FAILED cli/tests/test_poller.py::test_ledger_only_records_are_asked_longest_absent_first_up_to_the_cap
FAILED cli/tests/test_poller.py::test_unowned_and_degraded_ledger_only_records_do_not_spend_the_cap
FAILED cli/tests/test_poller.py::test_the_cycle_counts_ledger_checks - KeyErr...
FAILED cli/tests/test_poller_integration.py::test_a_closed_ledger_only_item_is_stamped_after_the_window
14 failed, 9 passed, 227 deselected in 1.49s
git stash pop
```

Three of the nine pass on the old code by design: `test_a_poll_only_record_with_a_future_timestamp_is_not_asked`
(A2 — the old code asked nothing, and neither does the new) and
`test_a_record_with_poll_beside_another_section_is_asked_without_a_window` ×3 (R2 — the
tracked set's rule is unchanged, and pinned).

| Task | Red (before the change) | Green |
|------|-------------------------|-------|
| 1 the schedule | no `absent_since` / `note_closure_check`; no `ledger_checks` on the summary or on `poll.cycle` | `test_poll_state_absent_since_is_the_later_timestamp`, `test_poll_state_note_closure_check_writes_through`, `test_the_cycle_counts_ledger_checks`; `test_eventlog.py::test_every_emitted_event_type_is_documented` |
| 2 the set and the question | a `poll`-only record was never asked; nothing dated a non-closure | the eleven remaining `test_poller.py` tests above; the integration scenario |
| 3 docs | — | `make lint` (markdownlint over every `*.md`), `test_docs_parity.py` |

Existing assertions changed: one — `test_a_poll_only_record_is_not_reconciled` pinned
issue-329's R3.2, the rule this work item relaxes, and is now the pair
`test_a_poll_only_record_seen_this_window_is_not_asked` /
`test_a_closed_ledger_only_item_is_forgotten_and_never_asked_again`. One pre-existing
test was made robust, not changed in what it proves:
`test_one_repository_with_issues_disabled_does_not_blind_the_others` (issue-315) asserted
the session record right after waiting for the tmux spawn, while the dispatcher
registers after it spawns, on its own thread — it failed 3 of 20 runs on the unchanged
source, and 0 of 20 once the assertion waits for the record as it waited for the spawn.

## Rows T1, T3, T9, T11

```text
== T1
uv run --project cli python -m pytest -q cli/tests/test_poller.py -k "ledger or poll_only or closure_check or absent_since"
21 passed, 199 deselected in 0.37s
== T3
uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py -k ledger
3 passed, 27 deselected in 0.60s
== T9
uv run --project cli python -m pytest -q cli/tests/test_poller.py cli/tests/test_poller_integration.py -k "ledger or poll_only or closure_check or absent_since"
24 passed, 226 deselected in 0.47s
== T11
uv run --project cli python -m pytest -q cli/tests/test_eventlog.py cli/tests/test_docs_parity.py
19 passed in 0.94s
== the two poller suites, whole
uv run --project cli python -m pytest -q cli/tests/test_poller.py cli/tests/test_poller_integration.py
250 passed in 3.07s
```

## Row T13 — `make check`

```text
make check
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Linting: 1016 file(s)
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
3200 passed, 1 skipped in 175.77s (0:02:55)
```

The dashboard's three commands (`cd ui && bun run lint && bun run test && bun run build`)
were not run: no file under `ui/` changed (T2 is n/a).

## Security

See [`security-review.md`](security-review.md) — abuse cases A1–A4, each closed by a
named test; no human sign-off at tier 3.
