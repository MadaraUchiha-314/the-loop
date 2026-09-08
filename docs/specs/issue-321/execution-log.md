---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#321"
phase: needs-review
status: in-progress
---

# Execution Log: a channel's gate answer reaches the gate

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-08 | — | Tier 3 (`human-approves-pr`; below `security.review.humanSignOffMinTier: 4`): the change lives in `cli/the_loop/channels/inbound.py`, one attribution line in `channels/github.py`, one event-log field, tests and docs; no new grant, no schema, workflow or sensitive path is touched. Brainstorming skipped — the ticket names the defect, the reproduction and two fix options. No authorized `the-loop execute` reaches this cloud session, so the selection is recorded here and every phase is walked |
| requirements-definition | 2026-09-08 | | [`bugfix.md`](bugfix.md) — root cause confirmed against real state; three requirements, five abuse cases |
| design | 2026-09-08 | | [`design.md`](design.md) — the dispatcher's own coupling as the reader, a three-valued read, deferral to the ledger within the grant; [`decision-109`](../../decisions/decision-109.md) |
| test-planning | 2026-09-08 | | [`testing-plan.md`](testing-plan.md) — thirteen rows, six applicable |
| tasks-breakdown | 2026-09-08 | | [`tasks.md`](tasks.md) — five tasks |
| implementation | 2026-09-08 | | On `claude/github-issue-321-tipucc` |
| verification | 2026-09-08 | | [`evidence/verification.md`](evidence/verification.md) — rows T1, T2, T8, T10, T12; [`evidence/security-review.md`](evidence/security-review.md) — five abuse cases, five closed |
| needs-review | 2026-09-08 | | PR raised; awaiting the owner (tier 3: `human-approves-pr`) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#323](https://github.com/MadaraUchiha-314/the-loop/pull/323) | tasks 1–5: the whole work item | open |

## Progress entries

### 2026-09-08 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–5, red first. The two T2 scenarios (red at `ba0c433`: the approval
  was delivered into the session as a marked reply); `_graph_reader` — the dispatcher's
  own construction of the coupling, from `RoutingConfig` over the same config and
  layout; the three-valued `_at_human_gate`; `_classify` with the grant-bounded
  deferral and the `gate` word; `classify(grants)` kept for callers; the `gate` field
  on `channel.reply_received` and its catalog description; the relay's *reply*
  attribution for a deferred record; eleven unit tests; the config reference, the
  capability doc, the collaboration reference, decision-109.
- **Checkpoint/tests:** `make check` — see `evidence/verification.md`. New tests: 11
  unit, 2 scenarios. No existing assertion changed.
- **Self-review:** three passes over the diff. Fixed in place: two unused imports in
  the new tests (ruff caught them); a test helper that declared a `read` parameter it
  never used — the read is patched by the caller, and a signature that claims
  otherwise misleads the next author. Considered and left: `RoutingConfig.from_mapping`
  warns about a removed `routing.runner` key, now once per reply instead of once at
  daemon start for an operator who still carries that key — the daemon already tells
  them to delete it. Pass three found nothing new.
- **Next:** the owner's review.
- **Blockers:** none.

### 2026-09-08 — spec chain drafted

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** read `channels/inbound.py`, `channels/github.py`, `graphlink.py` (`_guarded`,
  `_awaiting_start`, `context`), `webhook/dispatcher.py` (`RoutingConfig`, the coupling's
  construction, the consult-first gate path), `graph/hooks/feedback.py`, the router's
  and poller's marker checks, and issue-309's design at `ba0c433`; reproduced the report
  with a scratch script — a real checkout with `origin`, a registry record, a
  `graph-state.json` parked at `requirements-approval`, a recorded `start`: the
  dispatcher's read says `at_human_gate: True`, the pipeline's says `False`. Root cause:
  the pipeline builds its `GraphLink` without the control store, so `_guarded` reports
  every item as never started. Wrote the four artifacts and the decision.
- **Checkpoint/tests:** baseline — `test_channels.py` + `test_bus_integration.py` green
  (70 passed).
- **Next:** task 1 (the two T2 scenarios), red first.
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
| 1 | self | the-loop (this session) | new findings — two unused imports; a misleading test-helper parameter: fixed | this log |
| 2 | self | the-loop (this session) | zero (converged) | this log |
| 3 | self | the-loop (this session) | zero (converged) | this log |
| — | critic | — | unavailable — `reviews.critics` is empty in this repository's config; does not count toward `criticReviewCount` | — |
| 4 | security | the-loop checklist | pass; no human sign-off at tier 3 | [`evidence/security-review.md`](evidence/security-review.md) |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no security-review
  skill is invocable from this session's plugin set)
- **Outcome:** pass — [`evidence/security-review.md`](evidence/security-review.md), five abuse cases closed
- **Human sign-off:** n/a (tier 3 is below `humanSignOffMinTier: 4`)

## Final validation evidence

| Requirement | Proof |
|-------------|-------|
| R1.1 an approval from Slack reaches the gate under the default control policy | `Scenario: An approval from Slack reaches the gate under the daemon's default control policy` (red at `ba0c433`) |
| R1.2 the reader is the dispatcher's construction | `test_the_pipeline_reads_the_graph_through_the_dispatchers_own_coupling` |
| R1.3 "cannot tell" + the grant → unmarked `gate.feedback` | `test_an_unreadable_gate_defers_to_the_ledger_when_the_channel_may_answer_gates`, `test_no_session_record_is_an_unknown_gate_not_a_closed_one`, `test_a_graph_fault_is_cannot_tell`; `Scenario: A reply for a work item with no session record is left to the ledger` |
| R1.4 "cannot tell" without the grant → the marked reply | `test_an_unreadable_gate_without_the_grant_is_a_marked_reply_as_before`; the second half of the same scenario |
| R1.5 coupling off → a reply | `test_a_disabled_graph_coupling_means_no_gate_to_answer` |
| R1.6 a definite "no" → a reply | `test_a_graph_that_says_not_at_a_gate_keeps_the_reply_direct` |
| R1.7 keyword outranks | `test_a_control_keyword_outranks_an_unreadable_gate` |
| R1.8 regression test over real state | the first scenario: `git init` + `origin`, a registry record, `graph-state.json`, a recorded `start` |
| R2.1 `gate` on `channel.reply_received` | `test_the_reply_event_says_what_the_gate_read_returned` |
| R2.2 a deferred record is attributed as a reply | the deferral unit test and the second scenario (`"reply from" in body`) |
| R3.1 docs | `test_docs_parity.py`; `make lint` |
| A1–A5 | `evidence/security-review.md` |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`channels.md`](../../capabilities/channels.md) | a new current-behaviour bullet: the gate is read through the dispatcher's own coupling; the three answers; "cannot tell" deferred to the ledger within the grant, attributed as a reply; `gate` on `channel.reply_received`; what was true before | issue-321 row |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/config/cli/channels-options.md` | the `gate.feedback` row of the grants table (when a message becomes it; the "reply from" attribution) and the paragraph under it: the three-valued read, the deferral within the grant, the event-log field — replacing the sentence that called "no session, no graph coupling" the fail-closed direction |
| `skills/the-loop/reference/collaboration.md` | § 1: the gate is read through the dispatcher's coupling and a gate the pipeline cannot read is deferred under the same grant |
| `docs/decisions/decision-109.md`, `decisions.md` | the decision and its index row |
| `cli/the_loop/eventlog.py` | the `channel.reply_received` catalog description (`kind`, `gate`) — the text `the-loop events --types` and the reference print |
| `README.md`, `skills/the-loop/SKILL.md` | unchanged — neither describes how a channel reply is classified |
