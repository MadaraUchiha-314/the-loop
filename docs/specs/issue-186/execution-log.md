---
type: execution-log
workItem: issue-186
phase: needs-review
status: in-progress
---

# Execution Log: clean up after a work item is closed

> Append-only log for [#186](https://github.com/MadaraUchiha-314/the-loop/issues/186).

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-09 | pending — PR gate | Risk tier 4: a new control keyword (trust boundary), two schema edits, and a verb that deletes local data |
| design | 2026-08-09 | pending — PR gate | One module, one keyword, one graph node |
| test-planning | 2026-08-09 | pending — PR gate | 13-row matrix; git exercised for real, tmux faked at the existing seam |
| tasks-breakdown | 2026-08-09 | pending — PR gate | 10 tasks, each naming its matrix row |
| implementation | 2026-08-09 | — | All 10 tasks complete |
| verification | 2026-08-10 | — | Every applicable row executed; see `testing-plan.md` § Verification results |
| needs-review | 2026-08-10 | pending | Self-review done; human gate is the PR |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#189](https://github.com/MadaraUchiha-314/the-loop/pull/189) (this repository) | Tasks 1–10 — the whole work item | open |

## Progress entries

### 2026-08-09 — spec chain locked

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** Read the ticket and its follow-up comment, then the operating model
  (`harness-config.yaml`, the skill, `reference/workflow.md`) and the code the change
  lands in: `control.py`, `reset.py`, `workspace.py`, `sessions/registry.py`, the
  dispatcher's close path, `graphlink.py`, `graph/runtime.py` and the three shipped
  loops. Wrote and locked `requirements.md` → `design.md` → `testing-plan.md` →
  `tasks.md`.
- **Checkpoint/tests:** none yet (no code).
- **Next:** implement tasks 1–10.
- **Blockers:** none.

### 2026-08-09 — implementation

- **Phase:** implementation
- **Did:** All ten tasks. New `the_loop.cleanup` module (order + reporting, two injected
  seams); `cleanup` control command with `TEARDOWN_COMMANDS`; `Dispatcher.cleanup_work_item`
  plus `_end_endpoint` / `_remove_checkout`; the two ingress triggers (keyword, authorized
  closure); the terminal `cleanup` node in both work-item-level loops with
  `Runtime.cleanup` and `GraphLink.on_cleanup`; the verb across CLI/HTTP/MCP; both
  schemas, both shipped configs and both templates; and the documentation set.
- **Checkpoint/tests:** `make check` green — 1629 passed, 1 skipped, 0 lint/pyright
  findings.
- **Next:** self-review.
- **Blockers:** none.

### 2026-08-10 — self-review and verification

- **Phase:** verification → needs-review
- **Did:** Three self-review passes over the diff. Round 1 found the GitHub Enterprise
  defect described below and two smaller things (the `_apply_control` effect swallowed a
  partial failure; `GraphLink`'s action label rendered as "cleanuping" in an operator-facing
  log line). Round 2 checked the surfaces a new control verb has to reach and found the MCP
  tool docstring, `commands/init.md`'s label list and `docs/cli/state.md` still describing
  four verbs. Round 3 found nothing new — the stop condition
  (`reviews.stopOnNoNewFindings`).
- **Checkpoint/tests:** every matrix row executed; evidence committed under `evidence/`.
- **Next:** human review on the PR.
- **Blockers:** none.

## Verification results

Recorded in [`testing-plan.md`](testing-plan.md) § Verification results — this work item
locked a testing plan, so the matrix rows and their outcomes live there.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop | new findings — GHE checkout lookup missed a non-default host; a partial cleanup reported `cleaned`; a malformed log verb | fixed in-branch, regression test `test_a_github_enterprise_work_item_finds_its_own_checkout` |
| 2 | self | the-loop | new findings — three documentation surfaces still described four control verbs (MCP tool docstring, `commands/init.md`, `docs/cli/state.md`) | fixed in-branch |
| 3 | self | the-loop | zero (converged) | — |
| 4 | critic | — | **unavailable** — `reviews.critics` is empty in this repository's config, so no critic harness is configured to run. Does not count toward `criticReviewCount` | `.the-loop/harness-config.yaml` |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; the bundled
  security-review skill reviews *pending changes on the current branch*, and its findings
  are folded into the self-review rounds above).
- **Outcome:** pass. The change adds one trust boundary — comment text reaching a
  **destructive** daemon action — and it is enforced exactly where the existing control
  commands enforce theirs: after the self-authored marker check and the ingress
  `authorizedUsers` check, then re-checked against a named allowlisted actor in
  `_apply_control`, which fails closed on an absent or unallowlisted author. The parser
  yields one of the declared constants and never a substring of the body, and the work
  item acted on comes from the router's own extraction, so no payload text reaches a path,
  an argv or a prompt. The second boundary — a **close action with no identity**, the
  concern the ticket itself raises — also fails closed: cleanup is deferred and recorded
  rather than performed. No new filesystem path derivation was introduced; cleanup calls
  the same `Workspace.cleanup` the close path already calls, on a slug built from a
  validated ref. Blast radius is bounded by construction: the portable record, the event
  log, the committed spec tree and every remote object are outside its reach, and
  `cleanup.py` importing `WorkItemStore` is asserted against by a test rather than left to
  review. Negative tests for all four abuse cases pass (T8).
- **Human sign-off:** required — risk tier 4 ≥ `security.humanSignOffMinTier` (4).
  **Pending** on the PR.

## Final validation evidence

Every acceptance criterion has a test, and every test passed (`evidence/`):

| Requirement | Proved by |
|---|---|
| R1.1–R1.3 — tmux, checkout and local record go | `test_it_ends_every_endpoint_removes_the_checkout_and_the_record`, `test_an_authorized_comment_releases_every_local_resource` |
| R1.4 — the portable record survives | `test_the_portable_record_survives_a_cleanup`, `test_the_cleanup_module_never_reaches_the_portable_store`, `test_the_portable_record_and_the_shared_clone_survive` |
| R1.5 — nothing remote | no remote call exists on the path; the shared clone is asserted intact |
| R1.6 — absent pieces and partial failure | `test_a_tmux_session_that_was_already_gone_…`, `test_one_stuck_endpoint_does_not_strand_…`, `test_a_failing_checkout_removal_still_removes_the_record` |
| R2.1–R2.4 — the keyword | `test_cleanup_is_a_declared_command_with_its_own_keyword`, `test_an_empty_keyword_disables_only_cleanup`, `test_the_keyword_is_executed_not_forwarded_to_the_harness`, `test_abuse_an_unauthorized_commenter_cannot_ask_for_cleanup`, `test_recording_cleanup_disarms_the_work_item` |
| R2.5 — CLI / HTTP / MCP | `test_cleanup_is_one_of_the_control_verbs`, `test_cleanup_reports_each_irreversible_fact_on_its_own_line` |
| R3.1–R3.4 — closure | `test_a_closure_by_an_authorized_user_cleans_up`, `test_abuse_a_closure_naming_no_actor_defers_the_cleanup`, `test_abuse_a_closure_by_an_unauthorized_actor_…`, `test_abuse_a_merged_pull_request_never_cleans_up_its_work_item` |
| R4.1–R4.3 — retroactive | `test_a_checkout_with_no_session_record_is_still_reclaimed`, `test_cleanup_after_a_deferred_closure_finishes_the_job`, `test_a_work_item_with_nothing_left_reports_nothing_to_clean`, `test_a_github_enterprise_work_item_finds_its_own_checkout` |
| R5.1–R5.4 — the graph phase | the whole of `test_graph_cleanup.py` (17 tests) |
| R6.1–R6.2 — the record | `test_a_cleanup_emits_one_event_naming_the_actor_and_the_source`, `test_the_event_log_names_what_went`, the two deferral tests |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `docs/capabilities/interactive-sessions.md` | Two new behaviour rules: what a cleanup releases (and what it keeps), and the authorized-closer condition on doing it automatically | issue-186 |
| `docs/capabilities/webhook-triggers.md` | The seventh control keyword and the deferral rule; `cleanup` added to the disarming set | issue-186 |
| `docs/capabilities/process-graph.md` | The terminal `cleanup` node in both work-item-level loops, why it has no inbound edge, why it is not a force, and the one exemption from the start requirement | issue-186 |
| `docs/capabilities/cli.md` | `sessions cleanup` as the fifth control verb | issue-186 |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/config/cli/routing-options.md` | `control.keywords.cleanup` — the option, the danger note, and what it does not touch |
| `docs/cli/commands/sessions.md` | The `cleanup` subcommand, its output, the piece-by-piece table, and a `cleanup` vs `reset` comparison |
| `docs/cli/state.md` | A "Releasing a finished work item" section beside the reset one; `control.command` now lists `cleanup` |
| `docs/reports/labels-and-dashboards.md` | `loop:cleanup` in the phase chain, the label table and the `gh label create` block |
| `skills/the-loop/reference/automation.md` | The fifth keyword and what it releases |
| `commands/init.md` | The label list now names `loop:cleanup` |
| `skills/the-loop/templates/cli-config.yaml`, `harness-config.yaml` | The new keyword and the new phase, with their warnings |
