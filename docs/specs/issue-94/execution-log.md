---
type: execution-log
workItem: "issue-94"
phase: needs-review
status: in-progress
---

# Execution Log: closing a work item ends its harness session

> Append-only log of progress for the user's visibility. Checked in alongside
> the spec at `docs/specs/issue-94/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-25 |  | Issue #94: the poller never reacts to an issue close / PR merge, so the session and its tmux-hosted `claude` keep running. Investigation found two further gaps (webhook `issues`/`closed` is delivered as a prompt; a retained session keeps a **live** TUI). |
| design | 2026-07-25 |  | Provider closure contract + registry-driven poll reconciliation; generalised close event; `TmuxRunner.terminate_harness` turning a retained session into a dead, read-only pane. |
| tasks-breakdown | 2026-07-25 |  | 13-task DAG |
| implementation | 2026-07-25 |  | Implemented on `claude/github-issue-94-g0u10y` |
| needs-review | 2026-07-25 |  | PR opened with the reviewer briefing; `make check` green; awaiting human review (tier-3, `human-approves-pr`) |
| complete |  |  |  |

## Progress entries

### 2026-07-25 — investigation + spec drafted

- **Phase:** requirements-definition → design → tasks-breakdown
- **Did:** Traced both ingress paths. The poller lists `--state open` only, and
  its whole per-item loop runs over that listing — a closed/merged item just
  vanishes from it, and nothing compares the listing against the session
  registry, so the session stays `active` forever. The webhook path auto-closes
  on `pull_request`/`closed` only; `issues`/`closed` falls through to normal
  routing and is *delivered into the conversation* as an event prompt. And since
  issue-86 a closed work item's tmux session is **retained with the harness
  still running**, so `loop-<slug>` remains a writable `claude` TUI — the "stray
  input" the issue calls out. Designed: an opt-in provider closure contract
  (`owns`/`closure`/`closure_event`) so the poller core stays provider-agnostic;
  registry-driven reconciliation (stateless, survives poller downtime, one API
  call per session whose item left the listing); one generalised close event
  shared by both ingress paths; and `terminate_harness` (SIGTERM → SIGKILL after
  a grace) with `remain-on-exit` re-set first, so the retained pane becomes the
  read-only record the issue asks for instead of a live agent.
- **Next:** implement T1–T13.
- **Blockers:** none. Tier 3 (`human-approves-pr`): spec + code approved together
  at the PR.

### 2026-07-25 — implemented (T1–T13)

- **Phase:** implementation → needs-review
- **Did:**
  - `poller/base.py`: `Closure` + the opt-in provider trio `owns` / `closure` /
    `closure_event` (defaults = "this provider does not answer closure
    questions", so the poller core stays provider-agnostic and nothing else had
    to change).
  - `poller/github.py`: `GhItemState` + `GhClient.fetch_item_state` over
    `gh api repos/{o}/{r}/issues/{n}` — one endpoint for both kinds, with
    `pull_request.merged_at` separating merged from closed — and the provider's
    scope-checked `owns`, `closure`, and webhook-shaped `closure_event`
    (`poll-close-<ref>-<state>`).
  - `poller/poller.py`: `open_refs` collected from the (successful) listing
    including each item's *linked* refs, `_reconcile_closures` walking the
    **registry** rather than diffing listings, `PollSummary.closures`,
    `PollState.forget` (a reopened item is first-sight again).
  - `webhook/dispatcher.py`: `_is_pr_close` → `_is_close_event` + `_close_reason`
    (`issues`/`closed` now ends the work item too, instead of being delivered
    into the conversation), `reason` on `session.autoclosed`, and `_close_tmux`
    ending the harness before retaining.
  - `webhook/router.py`: the PR-close authorization exemption widened to
    `issues`/`closed` — narrowly, only the `closed` action.
  - `runner.py`: `live_pane_pids` + `terminate_harness` (re-set `remain-on-exit`,
    SIGTERM, stepped grace loop, SIGKILL), with the two guards the security pass
    added: the target must match `^loop-[A-Za-z0-9._-]+$` before any pane is
    listed, and non-positive pids are dropped before `os.kill`.
  - `commands/sessions_cmd.py`: `_tmux_config()` replacing `_default_keep_tmux`,
    `sessions close` ending the harness on the retain path, and
    `sessions attach` forcing `-r` for a closed session.
  - `eventlog.py`: `poll.closure_detected` and `session.harness_terminated`
    registered; `session.autoclosed`/`poll.cycle` descriptions updated.
  - Config: `killHarnessOnClose` / `harnessKillGraceSeconds` under
    `routing.tmux` in the schema, the dogfood cli-config and the packaged
    template.
  - Tests: unit (provider closure/owns/closure_event over canned `gh api` JSON,
    `PollState.forget`, `TmuxConfig` parsing, `_is_close_event`/`_close_reason`,
    the router exemption, `terminate_harness` × 8, `live_pane_pids` guards,
    `sessions attach`/`close`) and integration with Gherkin docstrings (five
    poll-cycle closure scenarios, the webhook `issues`/`closed` scenario, and
    stub-tmux close scenarios for both close kinds plus the opt-out). The stub
    tmux learned to answer the pid-carrying `list-panes` format and to report a
    pane dead once the fake `os.kill` has fired.
  - Docs: `cli/README.md` (two `routing.tmux` rows, the poll reconciliation
    bullet, the auto-close bullet), `docs/capabilities/interactive-sessions.md`
    and `docs/capabilities/webhook-triggers.md` (behaviour bullets + history
    rows), and the webhook event prompt (its parenthetical said PR-close only).
- **Checkpoint/tests:** `make check` green — ruff, markdownlint (214 files),
  `ruff format --check`, pyright 0 errors, all six config files VALID,
  pytest **385 passed**.
- **Next:** open the PR with the reviewer briefing; request review.
- **Blockers:** none.

## Review cycles

| Cycle | Type (self/critic) | Reviewer | Outcome | Link |
|-------|--------------------|----------|---------|------|
| 1 | self | the-loop (implementing agent) | Two findings, both fixed: (a) `killer=os.kill` as a **default argument** binds at import time, so the injected/monkeypatched `os.kill` never applied — the integration scenario proved it by escalating to SIGKILL against a stub that had already "died"; resolved per call instead (`killer or os.kill`). (b) `sessions attach` only *noted* that a session was closed while still attaching writable — now forced read-only, with a regression test for the active case keeping `--read-only` opt-in. | this PR |
| 2 | self (security lens, `security.review.mechanism: auto`) | the-loop (implementing agent) | One finding, fixed: `terminate_harness` took `session.tmux_target` from the registry and signalled whatever panes tmux reported for it — so a corrupted or hand-edited registry file could aim a SIGTERM/SIGKILL at the operator's *own* tmux session (the same class of finding as issue-89's flag-shaped session id). Added the `^loop-[A-Za-z0-9._-]+$` target check before any pane is listed, plus a hard drop of non-positive pids (`os.kill(0, …)` signals the caller's whole process group), with parametrised tests for both. Risk tier 3 < `security.review.humanSignOffMinTier` (4), so no named human security sign-off is required. | this PR |
| 3 | self | the-loop (implementing agent) | No new findings. Verified the fail-closed paths hold end to end: reconciliation runs only after a successful listing (the `ProviderError` path returns first), an unanswerable `closure()` leaves the session active, and an in-flight spawn is simply not yet in the registry so a closure it races with is caught on a later cycle. Also confirmed a close event still never renders a prompt (the close branch returns before templating) and never spawns. | this PR |
| 4 | self | the-loop (implementing agent) | No new findings — stopped per `reviews.stopOnNoNewFindings`. `reviews.critics` is empty in this repo's config, so no critic harness is configured to run. | this PR |

## Final validation evidence

Local gate (`make check`) green in full: ruff clean, markdownlint 0 errors over
214 files, `ruff format --check` clean, pyright 0 errors, all six config files
VALID, pytest **385 passed**.

| AC | Evidence |
|----|----------|
| R1.1, R1.2 | `test_a_closed_issue_closes_its_session`, `test_a_merged_pr_closes_its_session` (poll integration) + `test_a_closed_item_closes_its_session` / `test_a_merged_pr_closes_its_session` (unit) |
| R1.3 | `test_a_still_open_item_that_left_the_listing_keeps_its_session`, `test_an_unreachable_github_never_closes_a_session`, `test_an_unanswerable_closure_leaves_the_session_running` |
| R1.4 | `test_a_failed_listing_never_reconciles` (no `gh api` call at all) and the listing-failure half of `test_an_unreachable_github_never_closes_a_session` |
| R1.5 | `test_a_reopened_item_spawns_a_fresh_session`, `test_poll_state_forget_drops_the_whole_ledger` |
| R1.6 | `test_a_session_outside_the_sources_scope_is_untouched`, `test_provider_owns_only_its_configured_scope` |
| R1.7 | `PollProvider.owns`/`closure` defaults + every pre-existing poller test staying green (a provider that has not opted in is never reconciled) |
| R2.1, R2.2 | `test_dispatcher_auto_closes_session_on_issue_close`, `test_dispatcher_issue_close_never_spawns`, `test_issue_close_auto_closes_session` (webhook integration), `test_dispatcher_still_resumes_on_issue_events_that_are_not_close` |
| R2.3 | `test_router_issue_close_bypasses_authz_for_cleanup` + `test_router_still_guards_non_close_issue_events` |
| R2.4 | `test_close_reason_names_why_the_work_item_ended` |
| R3.1, R3.2 | `test_closing_a_work_item_ends_the_harness_but_keeps_the_session` (both close kinds: SIGTERM to the pane pid, `remain-on-exit` set, no `kill-session`), `TestTerminateHarness::test_sigterm_ends_the_harness_and_keeps_the_pane`, `…escalates_to_sigkill_when_sigterm_is_ignored`, `…zero_grace_escalates_without_waiting` |
| R3.3 | `test_pr_close_kills_the_tmux_session_when_configured_off` (unchanged, still green) |
| R3.4 | `…already_dead_pane_signals_nothing`, `…missing_session_is_not_a_failure`, `…an_already_exited_process_is_not_a_failure`, `…a_harness_that_survives_sigkill_is_reported_not_raised` |
| R3.5 | `test_ending_the_harness_on_close_can_be_switched_off`, `test_close_can_leave_the_harness_running` |
| R3.6 | `test_only_the_loops_own_sessions_are_ever_signalled`, `TestLivePanePids::test_never_returns_a_pid_that_would_signal_a_process_group`, `…skips_dead_ones`, `…unreadable_pane_list_signals_nothing` |
| R3.7 | process-runner sessions untouched — `_close_tmux` is only called for `session.runner == "tmux"` (pre-existing guard), and the full pre-existing suite stays green |
| R4.1, R4.2 | `test_attach_to_a_closed_session_is_always_read_only`, `test_attach_to_an_active_session_keeps_read_only_opt_in` |
| R5.1 | `TestRoutingConfigRunner` defaults/parsing + `make validate` over the schema and both cli-config YAMLs |
| R5.2 | `eventlog.EVENT_TYPES` entries (`the-loop events --types` lists them) |
| R5.3 | `docs/capabilities/interactive-sessions.md`, `docs/capabilities/webhook-triggers.md` updated in this PR |
