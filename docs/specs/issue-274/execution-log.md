---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#274"
phase: needs-review
status: in-progress
---

# Execution Log: the-loop opens a pull request and tells nobody it opened it

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-20 |  | `bugfix.md` derived from the ticket; the owner had already chosen fix 1 on the ticket |
| design | 2026-08-20 |  | `design.md` |
| test-planning | 2026-08-20 |  | `testing-plan.md` |
| tasks-breakdown | 2026-08-20 |  | `tasks.md` |
| implementation | 2026-08-20 |  | tasks 1–7 |
| verification | 2026-08-20 |  | every activity in `testing-plan.md` ran; results and evidence recorded there |
| needs-review | 2026-08-20 |  | reviewer briefing posted on PR #276 |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| #276 | the whole work item — spec chain, the `link-pr` operation on its surfaces, the workflow rule, documentation and tests | open |

## Progress entries

### 2026-08-20 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** red run first (19 tests, 18 failing on the missing operation, 1 control holding
  the bug in place); then `core.sessions.link_pull_request` and its surfaces (CLI
  `sessions link-pr`, `POST /api/v1/sessions/link-pr`, the `link_pull_request` MCP tool,
  `sessions.link_pr` on the SDK), the authored OpenAPI contract, the workflow rule in the
  four places the labelling rule already lives, the capability/CLI/state/SDK docs and
  decision-098.
- **Checkpoint/tests:** `make test` — 2495 passed, 1 skipped (2476 on `main` at
  `50c2a27`, +19); 2501 passed, 1 skipped after rebasing onto `main` at `71e7dff`.
  `make lint`, `make format-check`, `pyright cli`, `validate_config.py` — all clean first
  run. Evidence under `evidence/`.
- **Next:** human review of PR #276.

### 2026-08-20 — rebased onto main at the author's request

- **Phase:** needs-review
- **Did:** rebased onto `main` at `71e7dff`. One conflict, in
  `docs/capabilities/webhook-triggers.md`'s history table: issue-273 added its row at the
  top while this branch added issue-274's. Both kept, newest first. Recorded in
  `bugfix.md` that the companion bug named in § Out of scope has now landed as
  issue-273 (#275), and that it does not close this one.
- **Checkpoint/tests:** `make test` — 2501 passed, 1 skipped. `make lint`,
  `make format-check`, `pyright cli`, `validate_config.py` — clean.
- **Next:** human review of PR #276.

### 2026-08-20 — spec chain locked

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** read the ticket and the owner's answer (fix 1); traced the four linkage sources
  in `webhook/router.py` and `sessions/registry.py` and confirmed the-loop's spec PR
  satisfies none of them; wrote `bugfix.md`, `design.md`, `testing-plan.md`, `tasks.md`.
- **Checkpoint/tests:** none yet — no production code changed.
- **Next:** task 1, the red run.

## Verification results

> This work item has a `testing-plan.md`; results are recorded there.

## Design critic review

> Not selected for this work item.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop | new findings — the SDK namespace was missing `link_pr`, and the testing plan named a parity test (`test_harness_usage.py`) that is not one | this PR |
| 2 | self | the-loop | zero (converged) | this PR |
| 3 | critic | — | unavailable: `reviews.critics` is empty in this repository's harness config, so no critic harness is configured to run | `.the-loop/harness-config.yaml` |
| 4 | security | the-loop (checklist) | pass, no findings | [`evidence/security-review.md`](evidence/security-review.md) |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`, the skill being
  unavailable in this session)
- **Outcome:** pass, no findings — [`evidence/security-review.md`](evidence/security-review.md)
- **Human sign-off:** n/a — effective risk tier 3, below `security.review.humanSignOffMinTier` (4)

## Final validation evidence

The acceptance criteria, mapped onto what proved them (raw record:
[`testing-plan.md` § Verification results](testing-plan.md#verification-results)):

| Criterion | Proved by |
|---|---|
| R1.1 — one implementation, every surface | `test_sessions_command_link_pr_*` (CLI), `test_api_contract_parity` + `test_api_routers_integration` (HTTP), `test_mcp_integration` (MCP), `test_p2_every_namespace_method_reaches_core` (SDK) |
| R1.2 — the PR is recorded and `session.pr_linked` emitted | `test_link_pull_request_records_the_pr_and_emits` |
| R1.3 — idempotent | `test_link_pull_request_is_idempotent` |
| R1.4 — no record, no write, exit 1 | `test_link_pull_request_without_a_session_record_writes_nothing` |
| R1.5 — a work item does not deliver itself | `test_link_pull_request_refuses_a_work_item_delivering_itself` |
| R1.6 — bare number, `#N`, and a cross-repository full ref | `test_link_pull_request_resolves_a_number_in_the_work_items_repository` (4 cases), `test_link_pull_request_accepts_a_pull_request_in_another_repository` |
| R1.7 — malformed input refused, nothing written | `test_link_pull_request_refuses_malformed_input` (6 cases) |
| R2.1–R2.3 — the workflow rule, in four places, best-effort | the diff to `skills/the-loop/reference/automation.md`, `commands/work-on.md`, `commands/execute-tasks.md`, `skills/the-loop/templates/execution-log.md` |
| R2.4 — the capability doc documents a binding the-loop writes | the diff to `docs/capabilities/webhook-triggers.md` and its history row |
| R3.1 — a regression test per layer | [`evidence/red.md`](evidence/red.md) (18 red) → [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) (all green) |
| R3.2 — the reproduction end to end, Gherkin | `test_a_review_comment_on_the_loops_own_spec_pr_is_lost_without_the_binding` and `…_reaches_the_session_once_recorded` |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `docs/capabilities/webhook-triggers.md` | the durable PR→work-item binding documented as a source the-loop **writes** at PR-open time, not only one the dispatcher infers; `session.pr_linked` names its second writer | issue-274 |
| `docs/capabilities/cli.md` | `sessions link-pr` added to the CLI surface, with what it refuses | issue-274 |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/cli/commands/sessions.md` | the `link-pr` action, its flags and when to run it |
| `docs/cli/service.md` | `link_pull_request` in the routed-operations table |
| `docs/api-specs/openapi/the-loop.v1.yaml` | `POST /api/v1/sessions/link-pr` and `SessionLinkPrBody` |
| `skills/the-loop/reference/automation.md` | the PR-open step: record every PR you open |
| `commands/work-on.md`, `commands/execute-tasks.md` | the same rule, beside the labelling rule |
| `skills/the-loop/templates/execution-log.md` | the **Pull requests** note carries the rule |
| `docs/cli/state.md` | `pullRequests` has a second writer: the session that opened the PR |
| `docs/sdk/reference.md` | `sessions.link_pr` |
| `docs/decisions/decision-098.md`, `docs/decisions/decisions.md` | the decision record and its index row |
