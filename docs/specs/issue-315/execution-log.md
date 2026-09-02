---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#315"
phase: needs-review
status: in-progress
---

# Execution Log: one repository's failure is that repository's

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-02 | — | Tier 3 (`human-approves-pr`): the change is confined to the poller, its heartbeat and the status surface; no schema, workflow or config file is touched. Brainstorming skipped — the ticket states the root cause and the expected behaviour; no skip was declared by the session, the full chain was walked |
| requirements-definition | 2026-09-02 | | [`bugfix.md`](bugfix.md) — three compounding defects, four requirements, four abuse cases |
| design | 2026-09-02 | | [`design.md`](design.md) — the contract lists in scopes, the GitHub provider quarantines one condition, the heartbeat names what was not polled; [`decision-106`](../../decisions/decision-106.md) |
| test-planning | 2026-09-02 | | [`testing-plan.md`](testing-plan.md) — twelve rows, seven applicable |
| tasks-breakdown | 2026-09-02 | | [`tasks.md`](tasks.md) — six tasks |
| implementation | 2026-09-02 | | On `claude/focused-gates-gceo7h` — tasks 1–6 |
| verification | 2026-09-02 | | [`evidence/verification.md`](evidence/verification.md) — `make check` clean; [`evidence/security-review.md`](evidence/security-review.md) — four abuse cases, four closed |
| needs-review | 2026-09-02 | | PR raised; awaiting the owner (tier 3) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#316](https://github.com/MadaraUchiha-314/the-loop/pull/316) | tasks 1–6: the whole work item | open |

## Progress entries

### 2026-09-02 — root cause confirmed, spec chain drafted

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** read the ticket's log excerpt against `poller/github.py::list_work_items`
  and `poller/poller.py::_poll_provider` at `04ca71a`; confirmed the one-pass /
  one-verdict shape; wrote the four artifacts and the decision.
- **Checkpoint/tests:** none yet.
- **Next:** task 1 (the contract), red first.
- **Blockers:** none.

### 2026-09-02 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–6, red first (the whole new-test set failed on
  `AttributeError: 'GitHubPollProvider' object has no attribute 'listing'` before
  any production change). `Listing`/`ScopeFailure`/`listing()`/`scope_of()` on the
  contract; the GitHub provider lists per repository with the disabled-Issues
  quarantine; the core records `poll.scope_error` / `poll.scope_degraded` /
  `poll.scope_recovered` and reconciles closures per scope; the heartbeat's three
  `scopes*` keys and `status`'s `degraded:` lines; the docs, the capability doc and
  decision-106.
- **Checkpoint/tests:** `make check` — see `evidence/verification.md`. New tests: 15
  provider/core, 3 heartbeat, 4 status, 1 integration scenario.
- **Self-review:** three passes over the diff. Fixed in place after round 1: the
  classifier matched `gh`'s message case-sensitively (now lower-cased); the cycle
  line and the `poll.cycle` event counted degraded *entries*, so a repository with
  both listings failed counted twice (now distinct scopes). Round 2 (tests and
  docs): the re-probe test's second loop was one cycle long, so the recovery it
  asserted had already happened inside the loop — corrected; the reconciliation
  test asserted a registry state the recording dispatcher never produces —
  re-pointed at the close event. Round 3: zero new findings.
- **Next:** the owner's review.
- **Blockers:** none.

## Verification results

> Only when this work item declared `test-planning` away. It did not: results live in
> [`testing-plan.md`](testing-plan.md).

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
| — | — | — | see `testing-plan.md` |

## Design critic review

> Not selected for this work item.

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| | | | | |

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (this session) | new findings — case-sensitive classifier, degraded entries counted twice: fixed | this log |
| 2 | self | the-loop (this session) | new findings — two test expectations wrong about the doubles: fixed | this log |
| 3 | self | the-loop (this session) | zero (converged) | this log |
| — | critic | — | unavailable — `reviews.critics` is empty in this repository's config; does not count toward `criticReviewCount` | — |
| 4 | security | the-loop checklist | pass; no human sign-off required (tier 3) | [`evidence/security-review.md`](evidence/security-review.md) |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no security-review
  skill is invocable from this session's plugin set)
- **Outcome:** pass — [`evidence/security-review.md`](evidence/security-review.md), four abuse cases closed
- **Human sign-off:** n/a (tier 3 < `humanSignOffMinTier: 4`)

## Final validation evidence

| Requirement | Proof |
|-------------|-------|
| R1 per-scope fault isolation | `test_poller.py::test_listing_isolates_one_repositorys_failure`, `…::test_the_core_processes_the_healthy_scopes_items_beside_a_failure`, `…::test_reconciliation_skips_a_degraded_scope_and_keeps_the_rest`, `…::test_the_base_provider_lists_all_or_nothing_and_has_no_scope` |
| R2 a permanent condition, classified, surfaced once, re-probed | `test_poller.py::test_disabled_issues_is_permanent_and_still_lists_pull_requests`, `…::test_a_quarantined_repository_is_reprobed_every_sixty_cycles`, `…::test_only_ghs_own_message_classifies_as_permanent`, `…::test_a_permanent_failure_is_a_warning_and_a_skip_is_silent` |
| R3 `status` shows the degradation | `test_poll_heartbeat.py::test_the_heartbeat_carries_the_scopes_that_failed_or_were_skipped`, `test_poll_status.py::test_a_degraded_scope_is_named_beneath_the_last_cycle`, `…::test_a_cycle_where_nothing_answered_says_so`, `…::test_json_carries_the_degraded_scopes`, `…::test_a_clean_cycle_prints_no_degraded_line` |
| R4 regression test | `test_poller_integration.py::test_one_repository_with_issues_disabled_does_not_blind_the_others` |
| A1–A4 | `evidence/security-review.md` |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`cli.md`](../../capabilities/cli.md) | a behaviour bullet: a poll source lists in scopes, a scope fails alone, the one permanent condition, the heartbeat's scope facts and `status`'s `degraded:` lines | issue-315 row |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/config/cli/polling-options.md` | `sources[].repos`: one repository's failure is that repository's; the disabled-Issues classification, skip and re-probe |
| `docs/cli/commands/status.md` | the `degraded:` lines, with an example; the exit code unchanged; the JSON keys |
| `docs/cli/state.md` | the heartbeat's `scopesPolled` / `scopesFailed` / `scopesSkipped` keys |
| `README.md`, `skills/the-loop/SKILL.md` | unchanged — neither describes the poller's failure handling or the status line |
