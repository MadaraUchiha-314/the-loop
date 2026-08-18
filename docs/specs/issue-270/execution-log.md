---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#270"
phase: verification              # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress              # in-progress | complete
---

# Execution Log: a comment made before `the-loop start` is never delivered, and nothing says so

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| not-started | 2026-08-18 | — | ticket #270, split out of #269 § *Related casualty* |
| phase-selection | 2026-08-18 | — | see Deviations: the loop was run by hand in a cloud session, not by a daemon |
| requirements-definition | 2026-08-18 | pending | `bugfix.md` |
| design | 2026-08-18 | pending | `design.md` |
| test-planning | 2026-08-18 | pending | `testing-plan.md` |
| tasks-breakdown | 2026-08-18 | pending | `tasks.md` |
| implementation | 2026-08-18 | — | tasks 1–6, test-first per `tdd.mode: standard` |
| verification | 2026-08-18 | — | every activity in the testing plan ran; results recorded there |

## Pull requests

| Repository | PR | Loop state | Status |
|---|---|---|---|
| MadaraUchiha-314/the-loop | (this branch) | outer loop only — one repository, one delivery | open |

## Progress entries

### 2026-08-18 — the product decision was already made; the ticket names its two consequences

The ticket is explicitly a **product decision** ("a call for the owner, not for the loop"),
and the owner made it in a one-word comment: **Option-3** — the session re-reads the thread,
so the *content* of a pre-start comment is not lost; only the delivery accounting is wrong.
Option 3's own text carries the two things that then have to happen: *"it should be written
down, and `commentAttempts` should stop implying a pending retry."* This work item is those
two, and nothing else — no replay (option 1), no durable refusal marker (option 2).

### 2026-08-18 — reading the accounting turned up a worse tail than the ticket describes

The ticket says the comment "stays at `commentAttempts: 1` forever". True while the daemon
lives. Two things happen after that, and both are worse:

1. The dedup mark is a **process-local LRU**. On a restart — or after `dedupCacheSize`
   deliveries — `delivery_status` flips from `inflight` to `unhandled`, the poller spends
   attempts 2 and 3, and emits `poll.comment_failed` at error level *plus* a comment on the
   ticket telling the human their comment never reached the session after three attempts.
   Nothing was attempted; nothing failed.
2. That give-up is written into `gaveUp` with the CLI version, and `rearm_gave_up_comments`
   (issue-146) un-resolves anything a **different** version abandoned. So the first upgrade
   after the false give-up re-forwards the comment — **delivered late** if the item has been
   started by then. Today's behaviour is not "never replayed"; it is replay-on-upgrade,
   which is option 1's semantics arrived at by accident on a schedule nobody chose.

Recorded because it changes what "stop implying a pending retry" has to mean: the comment must
be **resolved**, and resolved as *baselined*, not as *given up*.

### 2026-08-18 — the fix, red→green, task by task

Written test-first: the 17 tests in [`evidence/red.md`](evidence/red.md) all failed before
any production code changed.

| Task | Red → green | What landed |
|---|---|---|
| 1 `Deduper` | `test_router_deduper_remembers_a_delivery_outcome` | the LRU's value is now the delivery's **outcome** (`add(id, outcome="")`, `mark_settled`, `outcome`) instead of `None`. One entry, one bound, one eviction |
| 2 the five sites | 8 tests in `test_routing.py` | `_settle()` at `_on_unmatched` (membership-gated on `SETTLED_SUPPRESSED`), the all-paused match in `handle`, `_dispatch_one`'s pre-dispatch pause, `_apply_control`, `_reject_control`, `control.ambiguous`; `delivery_status` → `settled` (after `done`), plus `delivery_outcome` |
| 3 catalogue | `test_eventlog.py` parity | `poll.comment_settled`, and `dispatch.dropped` / the `control.*` entries now say a suppressed or consumed delivery is reported to the poll path as settled |
| 4 the poller | 5 tests in `test_poller.py` | `_settle_comment` (baseline, **no** `gave_up`, no notice, one event), the two branches in `_process_comment`, the `settled` branch in `_try_spawn`, and `PollState`'s docstring on what `commentAttempts` counts |
| 5 the repro | 2 Gherkin scenarios in `test_poller_integration.py` | the ticket's reproduction across three cycles and a restart, and the upgrade that now re-arms nothing |
| 6 write it down | `test_the_spawn_prompt_tells_the_session_to_read_the_whole_thread` + `make lint` | the capability doc, `docs/cli/state.md`, `polling-options.md`, `reference/observability.md`, decision-097 — and the sentence in **both** spawn-prompt copies that makes option 3 true rather than merely stated |

Two decisions taken during implementation, both recorded in `design.md` §Trade-offs and
decision-097:

- **The three control outcomes settle too** (D7). `_apply_control` and `_reject_control`
  keep their delivery ids exactly as `awaiting-start` does, so a `the-loop stop` before any
  start was stuck in the ledger identically — and its restart tail is worse than a false
  notice: the poller re-forwards the comment and the-loop **executes the command again**.
  For `cleanup`, that releases local resources twice.
- **`session-occupied` was left alone** (D8). It looks like the same bug, but its stuck entry
  is what lets a redelivery succeed after the operator kills the stale tmux session.
  Baselining it would remove a recovery path to fix a cosmetic one.

### 2026-08-18 — one unrelated line: `uv.lock`

`uv.lock` still recorded `the-loopy-one 11.0.0` after the `11.0.1` bump commit; running the
suite relocked it. One line, matching the version already committed in `pyproject.toml`, kept
rather than reverted so the lockfile is not left stale.

## Capability docs

- [`docs/capabilities/webhook-triggers.md`](../../capabilities/webhook-triggers.md) — a new
  behaviour bullet ("an event refused on purpose is never replayed, and never counted as a
  pending delivery"), `delivery_status`'s new answer in the poll-retry bullet, and an
  `issue-270` history row.

## Documentation

- [`docs/cli/state.md`](../../cli/state.md) — `commentAttempts` counts only deliveries that
  may still be retried; a refused or consumed comment is baselined instead.
- [`docs/config/cli/polling-options.md`](../../config/cli/polling-options.md) —
  `maxRetries` counts only deliveries that could still succeed.
- [`skills/the-loop/reference/observability.md`](../../../skills/the-loop/reference/observability.md)
  — the question `poll.comment_settled` answers, next to `poll.comment_failed`.
- `skills/the-loop/templates/webhook-autoexecute-prompt.md` and `DEFAULT_SPAWN_TEMPLATE` —
  the spawned session is told to read the item's whole thread, including what was posted
  before the start. This is the user-facing half of the fix, not a doc chore: without it,
  "the content is not lost" rested on nothing.
- [`docs/decisions/decision-097.md`](../../decisions/decision-097.md) and the index.

## Deviations from the standard gates

- **The loop was walked by hand.** This is a Claude Code cloud session in the-loop's own
  repository, where the plugin's SessionStart hook does not fire and no daemon drives the
  graph (the gap `CLAUDE.md` exists to cover). The spec chain, the phase labels and this log
  were produced by following `skills/the-loop/SKILL.md` directly. No `phase-selection`
  checklist was posted and no `the-loop execute` was signed, because there was no daemon to
  post one — the artifacts stand in for the gate, and the human approval is the pull request
  review.
- **The critic rounds could not be run as specified.** `reviews.criticReviewCount: 3` asks
  for three rounds from a *different* harness/model, and `reviews.critics` is empty in this
  repository's config, so there is no critic to invoke (`the-loop critic run` has nothing to
  run). Three self-review rounds ran instead and are recorded above with what each found;
  the missing rounds are stated here rather than reported as done.
- **The security review used the checklist, not the skill.** `security.review.mechanism` is
  `auto`, which prefers a built-in security-review skill; the checklist is its shipped
  fallback and is what ran here, recorded as what it was.

## Security review

- [x] Checklist (`reference/security.md`), effective risk tier 3 → no named human security
  sign-off required (`humanSignOffMinTier: 4`); pass with no findings, one residual risk
  recorded — [`evidence/security-review.md`](evidence/security-review.md).
