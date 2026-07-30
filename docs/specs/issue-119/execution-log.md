---
type: execution-log
workItem: issue-119
phase: needs-review       # not-started | brainstorming | requirements-definition | design | tasks-breakdown | implementation | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: a start command that predates first sight is silenced by its own baseline

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-30 | pending (PR) | Bug, so `requirements.md` carrying the bug report (`type: bugfix`); no brainstorm — the reporter's diagnosis was exact and confirmed by tracing |
| design | 2026-07-30 | pending (PR) | Two candidate fixes named on the ticket; option B taken, A recorded as rejected |
| tasks-breakdown | 2026-07-30 | pending (PR) | 6-task DAG |
| implementation | 2026-07-30 | pending (PR) | T1–T6 |
| needs-review | 2026-07-30 | pending | Tier 3 ⇒ `human-approves-pr`; completes when the PR merges |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#120](https://github.com/MadaraUchiha-314/the-loop/pull/120) | spec + T1–T6 | open |

## Progress entries

### 2026-07-30 — spec written (bugfix → design → tasks)

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** Confirmed the root cause in the tree: `_process_item`'s first-sight branch
  calls `_try_spawn` (refused by `_awaiting_start`, correctly) and then
  `baseline_comments(ref, live_ids, …)`, which writes **every** live comment id into
  `seenComments`. The known-item candidate filter is `comment.id not in seen`, so the
  start comment is never handed to `Dispatcher.handle` — the only place `parse_command`
  runs and the only writer of the `ControlStore`. `start_requested` therefore stays
  False and `_awaiting_start` keeps refusing: a closed loop, `spawns: 0` forever.
  Wrote `requirements.md` (11 EARS ACs + threat-model-lite, risk tier 3), `design.md`
  (option B: don't baseline what nobody processed), `tasks.md`.
- **Checkpoint/tests:** none yet — no code written.
- **Next:** T1 — the integration regression test, red first.
- **Blockers:** none.

### 2026-07-30 — implementation complete (T1–T6)

- **Phase:** implementation → needs-review
- **Did:** `Poller._pending_control_ids(ref, comments)` (authorized, non-self,
  unambiguous, and only while the item has **no** control record) + the reworked
  first-sight branch: baseline everything else, `_try_spawn` only when nothing is
  pending, otherwise fall through to the ordinary comment path so the deferred
  commands are forwarded in thread order on the **same** cycle. Corrected
  `_awaiting_start`'s docstring, whose "the start still gets through as an ordinary
  comment event" was the false assumption this bug lived in.
- **Unplanned, in scope (AC11):** while tracing the pre-existing-`stop` case, the
  replay risk surfaced — the CLI's own `sessions start` posts a **self-marked**
  keyword comment (invisible to the predicate) while a human's earlier `stop` stays a
  plain comment, so a lost `poll-state.json` alongside surviving control records would
  have re-applied the stop and killed a running session. Gated the whole scan on
  "no control record yet": a first sight may bootstrap control state, never overwrite
  it. AC11 + a negative test added.
- **Checkpoint/tests:** `make check` green — `ruff check`, `ruff format --check`,
  `pyright` 0 errors, `markdownlint` 0 errors, `validate_config.py` VALID, pytest
  **821 passed, 1 skipped** (809 before this work item; +12 new). Red→green recorded:
  T1's three integration tests failed with `assert '' == 'stop'` /
  `assert 0 == len(adapter.spawns)` before T2 and pass after; the
  arm-exactly-once unit test failed on `['issues'] != ['issues', 'issue_comment']`.
- **Next:** human review of the PR (the tier-3 gate).
- **Blockers:** none.

### 2026-07-30 — CI's own gate rejected the spec's shape

- **Phase:** needs-review
- **Did:** The `the-loop gate` job failed on PR #120:
  `BLOCK requirements-definition · required artifact is missing
  (docs/specs/issue-119/requirements.md)`. Not test noise — a real mismatch in this
  repository's own process. The skill and `.the-loop/manifest.yaml` both bless
  **`bugfix.md`** in place of `requirements.md` for a bug (issues 36/78/80/93/104 all
  used it), but the shipped process graph does not: `pdlc.yaml`'s
  `requirements-definition` node declares `produces: [requirements.md]` literally, and
  `validate-artifacts` resolves `produces` with no alternative — so a bugfix-shaped
  work item can never clear the gate. The graph landed in issue-109, *after* every
  existing `bugfix.md`, so nothing had exercised the combination until now.
  Conformed rather than changed the shipped graph inside a poller bugfix: the phase-1
  artifact is `requirements.md` (front-matter still `type: bugfix`, and it still carries
  the reproduction / expected-vs-actual / root-cause sections a bug spec needs), with
  the exact section names the graph's exit hooks require — `Requirements`,
  `Security considerations` on phase 1; `Architecture`, `Security design`,
  `Testing strategy` on the design; `Task list` on the tasks. Raised the underlying
  mismatch on the PR as a follow-up.
- **Checkpoint/tests:** `uv run the-loop check issue-119 --recompute --fail-on block`
  → **exit 0**, work item at `requirements-approval` in `WAIT` ("no authorized feedback
  yet") — the correct state for an open PR, and the same shape issue-117 reports.
  `make check` still green.
- **Next:** unchanged — human review of PR #120.
- **Blockers:** none.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self (spec ↔ diff ↔ tests) | the-loop session | Found the control-record replay gap → AC11 | this log |
| 2 | self (blast radius of the fall-through) | the-loop session | Confirmed no double-spawn: arming decision taken once per cycle; `state.finalize` still runs | `test_a_deferring_first_sight_arms_the_spawn_exactly_once` |
| 3 | self (regression surface) | the-loop session | Whole suite green, first-sight behaviour unchanged when no command is pending | 821 passed |
| 4 | human (PR approval) | @MadaraUchiha-314 | pending | PR #120 |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`)
- **Outcome:** pass. The trust boundary (comment text → daemon action) does not move:
  `_pending_control_ids` returns comment **ids** and nothing else; parsing,
  the named-authorized-actor re-check, execution and recording all stay in
  `Dispatcher._apply_control`. The poller's own filter fails closed on the same two
  guards the known-item forward path applies (`is_authorized`, `is_self_authored`),
  each with a negative test (A1 stranger's start, A2 the-loop's own keyword comment);
  ambiguity and `control.enabled: false` also baseline as before. A3 (a start on an
  unarmed item) is untouched — `_spawn_refusal` still checks `spawn-policy` first and
  records nothing. AC11 additionally prevents replaying commands already acted on. No
  new dependency, subprocess, credential, network call or event type; work is one
  regex pass over comments already fetched, bounded by the existing
  `_SEEN_COMMENTS_CAP`.
- **Human sign-off:** not required — risk tier 3 < `security.review.humanSignOffMinTier: 4`.

## Final validation evidence

- **Test suite:** 821 passed, 1 skipped (809 before; +12 tests).
- **AC coverage:**
  - AC1/AC3/AC8 — `test_control_integration.py::test_a_start_comment_that_predates_first_sight_still_starts_the_item`
    (real `Dispatcher` + `ControlStore`: one spawn, `start` recorded, zero presence
    events) and `test_poller.py::test_first_sight_forwards_a_pre_existing_start_and_baselines_the_rest`.
  - AC2 — `test_pre_existing_control_comments_are_applied_in_thread_order`,
    `test_a_stop_that_predates_first_sight_leaves_the_item_disarmed`,
    `test_first_sight_forwards_pre_existing_commands_in_thread_order`.
  - AC4 — the pre-existing `test_first_sight_spawns_and_baselines_comments` still
    passes unchanged, plus `test_first_sight_with_control_disabled_is_unchanged`.
  - AC5 — the chat comment in
    `test_first_sight_forwards_a_pre_existing_start_and_baselines_the_rest` is
    baselined, not forwarded.
  - AC6 — `..._baselines_an_unauthorized_authors_start`,
    `..._baselines_the_loops_own_keyword_comment`,
    `..._baselines_an_ambiguous_control_comment`,
    `..._with_control_disabled_is_unchanged`.
  - AC7 — `test_first_sight_ignores_the_thread_of_an_unauthorized_items_author`.
  - AC8 — `test_a_deferring_first_sight_arms_the_spawn_exactly_once`.
  - AC9 — the integration test above, red before T2.
  - AC10 — `docs/capabilities/webhook-triggers.md` (current behaviour + history row).
  - AC11 — `test_first_sight_does_not_replay_a_thread_the_loop_already_acted_on`.
- **Regression check:** the whole poll suite (`test_poller.py`,
  `test_poller_integration.py`, `test_control_integration.py`) passes untouched — the
  first-sight path is bit-identical whenever no unprocessed control command is present,
  which is every pre-existing test.
