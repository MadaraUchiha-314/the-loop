# Verification — issue-315

> The testing plan executed (`testing-plan.md`, rows T1–T7). Commands run from the
> repository root at the head of `claude/focused-gates-gceo7h`. Fixture repositories
> (`octo/repo`, `octo/repo-m`) are not real; the `gh` message is the ticket's anonymised
> one. Nothing here needed redaction.

## Red → green

The whole new-test set was written first and run against `04ca71a` (the unchanged
poller). Every test failed at the same seam — the contract had no `listing()` — before
any production line changed:

```text
uv run --project cli python -m pytest -q cli/tests/test_poller.py … -k "scope or listing or …" -x
    def test_listing_isolates_one_repositorys_failure(tmp_path):
        runner = _two_repo_gh(issue_fail="HTTP 502: upstream")
>       listing = _two_repo_provider(runner).listing()
E       AttributeError: 'GitHubPollProvider' object has no attribute 'listing'
FAILED cli/tests/test_poller.py::test_listing_isolates_one_repositorys_failure
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
```

| Task | Red (before the change) | Green |
|------|-------------------------|-------|
| 1 contract | `AttributeError: … no attribute 'listing'` on every provider/core test | `test_poller.py` 246 passed (with heartbeat, status, integration, eventlog) |
| 2 provider | same seam; then two expectations corrected in self-review round 2 (the re-probe loop was one cycle long; a registry assertion the recording dispatcher never produces) | `-k "scope or listing or disabled or cycle_line"`: 21 passed |
| 3 core | `poll.scope_*` never emitted; `PollSummary` had no `scopes_*` | same run |
| 4 heartbeat / status | `test_record_then_read_round_trips` — the three new keys absent; `degraded:` lines absent | `test_poll_heartbeat.py`, `test_poll_status.py` pass |
| 5 integration | the scenario failed on the same seam | `test_poller_integration.py::test_one_repository_with_issues_disabled_does_not_blind_the_others` pass |
| 6 docs | — | markdownlint 942 files, 0 errors |

## `make check` — the way CI runs it (final tree)

```text
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/** !docs/specs/*/design/**
Linting: 942 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
274 files already formatted
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
2976 passed, 1 skipped in 167.38s (0:02:47)
exit=0
```

## Test matrix — results

| Row | Outcome | Evidence |
|-----|---------|----------|
| T1 | pass | `test_poller.py`: `test_listing_isolates_one_repositorys_failure`, `test_a_pull_request_listing_failure_is_isolated_too`, `test_a_repository_that_answers_nothing_is_not_polled`, `test_disabled_issues_is_permanent_and_still_lists_pull_requests`, `test_a_quarantined_repository_is_reprobed_every_sixty_cycles`, `test_only_ghs_own_message_classifies_as_permanent`, `test_the_strict_form_still_raises_on_any_failure`, `test_listing_without_repos_is_still_a_whole_provider_failure`, `test_scope_of_spells_the_repository_the_way_failures_do` (×4) |
| T2 | pass | `test_poller.py`: `test_the_base_provider_lists_all_or_nothing_and_has_no_scope`, `test_the_core_processes_the_healthy_scopes_items_beside_a_failure`, `test_a_permanent_failure_is_a_warning_and_a_skip_is_silent`, `test_reconciliation_skips_a_degraded_scope_and_keeps_the_rest`, `test_a_skipped_scope_is_not_reconciled_either`, `test_the_cycle_line_counts_degraded_scopes`; the pre-existing `test_provider_error_is_captured_not_raised` and `test_a_failed_listing_never_reconciles` unchanged and passing |
| T3 | pass | `test_poll_heartbeat.py` (3 new + the round-trip updated for the new keys), `test_poll_status.py` (4 new; the existing `status` assertions unchanged) |
| T4 | pass | `test_poller_integration.py::test_one_repository_with_issues_disabled_does_not_blind_the_others` |
| T5 | pass | `test_eventlog.py` — catalogue parity with the three new types |
| T6 | pass | see `security-review.md` |
| T7 | pass | `make check` above |
| T8–T12 | n/a | as planned |

## the-loop's own gate

```text
uv run the-loop check issue-315 --recompute --fail-on block
issue-315: UNMET (at phase-selection)
  WAIT   phase-selection
         · waiting for an authorized user to choose the phases and reply `the-loop execute`
gate exit=0
```

The pointer waits at the human gate, as every open pull request's does; nothing blocks.
