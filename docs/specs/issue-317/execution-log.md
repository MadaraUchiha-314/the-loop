---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#317"
phase: needs-review
status: in-progress
---

# Execution Log: the start opens the conversation

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-03 | — | Tier 3 (`human-approves-pr`; below `security.review.humanSignOffMinTier: 4`): the change lives in `cli/the_loop/channels/`, one seam of the dispatcher, the daemons' wiring, tests and docs; no schema, workflow or harness-config path is touched. Brainstorming skipped — the ticket's two bullets are the requirements |
| requirements-definition | 2026-09-03 | | [`requirements.md`](requirements.md) — the thread opens on the first event, minutes after the start; three requirements, five abuse cases |
| design | 2026-09-03 | | [`design.md`](design.md) — `open` on the channel, `open_conversation` on the bus, an injected opener on the dispatcher's spawn path; [`decision-107`](../../decisions/decision-107.md) |
| test-planning | 2026-09-03 | | [`testing-plan.md`](testing-plan.md) — thirteen rows, seven applicable |
| tasks-breakdown | 2026-09-03 | | [`tasks.md`](tasks.md) — six tasks |
| implementation | 2026-09-03 | | On `claude/github-issue-317-7mtlc5` |
| verification | 2026-09-03 | | [`evidence/verification.md`](evidence/verification.md) — rows T1, T2, T8, T10, T12; [`evidence/security-review.md`](evidence/security-review.md) — five abuse cases, five closed |
| needs-review | 2026-09-03 | | PR raised; awaiting the owner (tier 3: `human-approves-pr`) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#319](https://github.com/MadaraUchiha-314/the-loop/pull/319) | tasks 1–6: the whole work item | open |

## Progress entries

### 2026-09-03 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–6, red first each. `SlackBotChannel.open` (the issue-312 root under the
  same lock, origin `start`, no reply) and `_open_thread(…, origin)`; `start` in
  `CONVERSATION_ORIGINS`; the `Conversational` protocol beside `Channel`;
  `bus.open_conversation` (every conversational channel, best-effort, `channel.open_failed`);
  `publishers.conversation_opener` (config per call, the comment publisher's shape);
  `Dispatcher(opener=…)` called from `_spawn_for` after the adapter check and before the
  checkout; wired in `gh-webhook`, in the poller's `_build_dispatcher` (new
  `cli_config_getter`) and through it in the core facade with the config it was handed;
  the four scenarios; the docs, two capability docs, decision-107.
- **Checkpoint/tests:** `make check` — see `evidence/verification.md`. New tests: 6 unit
  (channel/state), 3 (bus/opener), 6 (dispatcher seam), 2 (facade/poll wiring), 4 scenarios.
  No existing assertion changed: the lazy path is untouched, so every issue-312 test
  stands as written.
- **Self-review:** three passes over the diff. Fixed in place: the open ran before the
  missing-adapter check (R1.4 names that refusal — moved behind it); the opener's inner
  function shadowed the bus's `open_conversation` (renamed); the restart scenario rebuilt
  a `RoutedEvent` from `__dict__` (now `dataclasses.replace`). Pass three found nothing
  new.
- **Next:** the owner's review.
- **Blockers:** none.

### 2026-09-03 — spec chain drafted

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** read the channel package, the dispatcher's spawn path and both daemons' wiring
  at `f56a71f`; found that every way of starting a work item converges on
  `Dispatcher._spawn_for`, and that the Slack root is opened only by the first event;
  wrote the four artifacts and the decision.
- **Checkpoint/tests:** baseline — the channel, bus and control test files green.
- **Next:** task 1 (`open` on the channel), red first.
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
| 1 | self | the-loop (this session) | new findings — the open ahead of the adapter check; the shadowed name; the `__dict__` rebuild: fixed | this log |
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
| R1.1 a start opens the conversation, before the checkout, from every entry point | `test_a_start_opens_the_conversation_once_before_the_checkout`; `Scenario: A start opens the work item's thread before any event`; `test_the_facade_dispatcher_opens_with_the_config_it_was_given`, `test_the_poll_builder_wires_an_opener_by_default` |
| R1.2 the root alone, no reply | `test_open_posts_the_root_alone_and_binds_with_origin_start` |
| R1.3 idempotent — a bound work item keeps its thread | `test_open_is_idempotent_for_a_bound_work_item`; `Scenario: A restarted work item keeps its thread` |
| R1.4 a refused start opens nothing | `test_a_refused_start_opens_no_thread`, `test_an_unauthorized_start_opens_no_thread`; `Scenario: A refused start opens no thread` |
| R1.5 best-effort, `channel.open_failed`, the lazy path as fallback | `test_a_failed_open_binds_nothing`, `test_a_failing_open_is_a_result_and_an_event_never_an_exception`, `test_a_raising_opener_never_fails_the_spawn`; `Scenario: A Slack outage never fails the spawn` |
| R1.6 the ledger and any channel without `open` are skipped | `test_open_conversation_opens_on_every_channel_that_can_and_skips_the_ledger` |
| R1.7 the first event is the first reply | `Scenario: A start opens the work item's thread before any event` (the ask lands as a reply) |
| R2.1 origin `start`, listed | `test_open_posts_the_root_alone_and_binds_with_origin_start`, `test_an_unknown_origin_is_coerced_to_event` (`channels threads` prints the origin column unchanged, issue-312) |
| R2.2 `channel.thread_opened` / `channel.open_failed`, ids only | `test_open_posts_the_root_alone_and_binds_with_origin_start`, `test_a_failing_open_is_a_result_and_an_event_never_an_exception`; `test_eventlog.py` catalog |
| R3.1 the bus is the only caller; config per call | `test_the_daemon_opener_reads_the_config_per_call_and_needs_a_channels_section` |
| R3.2 both daemons and the facade wire it; the facade with its own config | `test_the_facade_dispatcher_opens_with_the_config_it_was_given`, `test_the_poll_builder_wires_an_opener_by_default`; `gh-webhook` wired in `_build_routing` (no unit seam; the same `conversation_opener`) |
| R3.3 no opener, no change | `test_a_dispatcher_without_an_opener_opens_nothing` |
| A1–A5 | `evidence/security-review.md` |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`channels.md`](../../capabilities/channels.md) | a new current-behaviour bullet (the thread opens when the work item starts: every entry point, root only, idempotent, refused starts open nothing, best-effort with `channel.open_failed`, the injected opener); the observability bullet names the new event and the `start` origin; the Design list links this spec and decision-107 | issue-317 row |
| [`interactive-sessions.md`](../../capabilities/interactive-sessions.md) | a new current-behaviour bullet beside the announcement: the spawn path opens the work item's channel conversations first | issue-317 row |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/cli/commands/channels.md` | § One thread per work item: the thread opens when the work item starts; the lazy path as fallback; the `origin` column |
| `docs/cli/commands/sessions.md` | the `start` bullet: the channel conversation is opened first |
| `docs/cli/state.md` | the `start` origin in the `conversations` map |
| `docs/config/cli/channels-options.md` | the thread paragraph: opened at start, on every enabled channel, `channel.open_failed` as the fallback signal |
| `skills/the-loop/reference/collaboration.md` | one clause in the channels paragraph: opened the moment the work item starts |
| `docs/decisions/decision-107.md`, `decisions.md` | the decision and its index row |
| `README.md`, `skills/the-loop/SKILL.md` | unchanged — neither describes when the Slack thread opens |
