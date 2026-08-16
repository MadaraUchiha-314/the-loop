---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#251"
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
# repos:                     # OPTIONAL (issue-183). Single-repository work item.
---

# Execution Log: integration tests that wait on the attempt and assert on its outcome

> Append-only log of progress for the user's visibility. The-loop keeps the work item's
> phase label in the ticketing system in sync with the `phase` front-matter above, and
> self-checks (runs tests at logical checkpoints) recording the outcome here.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-16 | — (declared on the ticket, see below) | No daemon and no human on the thread; nothing was skipped. `brainstorming` and `design-critic-review` not run. |
| requirements-definition | 2026-08-16 | pending (PR) | `bugfix.md` — a bug. Written after the sweep, so the requirements name what was actually found rather than what the ticket predicted. |
| design | 2026-08-16 | pending (PR) | Three changes, and the argument for the third (ship the lag, don't only document the rule). Four rejected alternatives. |
| test-planning | 2026-08-16 | pending (PR) | 13 rows, 4 in scope; each `n/a` carries a reason. The chaos row (T9) is the regression test — a conventional one would be a test about a test. |
| tasks-breakdown | 2026-08-16 | — | 7 tasks; task 1 (the lag) is the red root both fixes are proved against. |
| implementation | 2026-08-16 | — | TDD: the lag option landed first and made both tests fail before either was touched. |
| verification | 2026-08-16 | — | Every activity ran; see `testing-plan.md` § Verification results. |
| needs-review | 2026-08-16 | | |
| complete | | | |

**On the phase-selection gate.** The loop's rule is that skips are declared by humans and
never taken by the harness, and that the gate is never answered from a working session.
This session was invoked directly on the issue with no daemon driving it and nobody on the
thread to answer, so the gate could not be *answered* — and blocking would have delivered
nothing. The rule was honoured in the only direction available: **nothing was skipped.**
The approval sits where the risk tier says it belongs — a human approving the PR
(`autonomy.defaultTier: 3` → `human-approves-pr`).

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#256](https://github.com/MadaraUchiha-314/the-loop/pull/256) | The whole work item — the sweep, both fixes, `--dispatch-lag`, and the rule. | open |

## Progress entries

### 2026-08-16 — the ticket's two tests were already fixed; the sweep was the open work

- **Phase:** requirements-definition
- **Did:** read the two tests the ticket names before writing anything. Both already carry
  the remedy: `test_a_labelled_work_item_does_not_spawn_until_it_is_started` waits on the
  registration (`cli/tests/test_control_integration.py:170`) and
  `test_spawning_for_a_linked_issue_records_the_binding` waits on the linkage
  (`cli/tests/test_webhook_routing_integration.py:755`). `git blame` puts both in
  `f9077b7` — [PR #244](https://github.com/MadaraUchiha-314/the-loop/pull/244), which also
  fixed a third instance it hit in CI and said so in its commit message: *"This is
  issue-251's remedy landing here rather than separately… That ticket stays open for the
  suite to be swept for the same pattern."*
- **Decided:** the deliverable is the sweep, not a re-fix. Recorded on the ticket.

### 2026-08-16 — reading 190 wait sites found candidates; running them found the truth

- **Phase:** requirements-definition
- **Did:** catalogued every `wait_until` / `_wait` / `time.sleep` site in `cli/tests/`
  (~190 across 18 files) and classified each against the dispatcher's actual write order
  (`_spawn_tmux`: spawn → register → touch → PR binding → event log → graph → announce;
  `_dispatch_one`: deliver → event log → touch → graph).
- **Found:** most of the suite is already disciplined. `dispatcher.stop()` is a genuine
  barrier — sentinel at the tail of each queue, then join — and the files that use it
  before asserting are correct by construction.
- **Found — reading is not enough.** Two of my hand-picked suspects were wrong, and
  proving it took an experiment rather than an argument. The best example:
  `test_labeled_issue_spawns_a_registered_session_once` carries the comment *"registry now
  has it -> must not spawn again"*, which reads exactly like the bug. Patching
  `SessionRegistry.register` to a no-op leaves the test passing that assertion — the second
  cycle is gated by the **poller's** own state, not the registry. The comment is
  misleading; the test is not racy.
- **Concluded:** this is a happens-before property, so the way to test it is to move time.

### 2026-08-16 — the whole suite, with every post-dispatch write delayed

- **Phase:** requirements-definition → design
- **Did:** ran all 2224 tests with `SessionRegistry.register/touch/save_endpoint/link_pull_request/close`,
  `Deduper.discard`, `SessionAnnouncer.announce`, `GraphLink.on_spawn/on_event` and
  `ControlStore.record` each delayed 0.5s.
- **Result:** **exactly two failures**, and neither is the variant the ticket describes.
  Both wait on a failed delivery and then *act* on its outcome — a re-POST that is deduped
  away, and a poll cycle that reads the delivery as still in flight. The assertion variant
  is extinct; the action variant was not being looked for.
- **Decided:** ship the lag as `pytest --dispatch-lag=<seconds>` rather than leave it in a
  scratch file. Argued in `design.md`, recorded as
  [decision-089](../../decisions/decision-089.md). The one-line case: PR #244 wrote this
  lesson into three code comments and two more instances were still in the suite.

### 2026-08-16 — red, then green, under the shipped flag

- **Phase:** implementation
- **Did:** landed `--dispatch-lag` first, confirmed both tests fail under it
  (`2 failed in 8.57s`), then fixed each to wait on what it depends on:
  `"e-1" not in server_factory.dispatcher.deduper`, and
  `dispatcher.delivery_status("poll-comment-IC_2", refs) == "unhandled"` — the very call
  the next poll cycle makes. Both `time.sleep` stand-ins deleted; the delivery-count checks
  stay as assertions, which is what they always should have been.
- **Self-check:** both files green under `--dispatch-lag=0.5` (42 passed).

### 2026-08-16 — three self-review rounds; the first one was the one that mattered

- **Phase:** verification → needs-review
- **Round 1 — could the new waits be *trivially* true?** The obvious way to fix a race
  badly is to wait on a predicate that is already satisfied before the work starts.
  `"e-1" not in dispatcher.deduper` would be exactly that if the id were marked late.
  Checked the ordering rather than assuming it: `Dispatcher.handle()` calls
  `deduper.add()` at its top, and the receiver's handler runs `on_event` **before** it
  sends 202 (`cli/the_loop/webhook/server.py:116-121`) — so the POST cannot return until
  the id is in. The poll path is the same by construction: `poll_once()` calls
  `dispatcher.handle()` synchronously, so `delivery_status` reads `"inflight"` the moment
  it returns. Both predicates can only become true through the discard the tests are
  waiting for.
- **Round 2 — does the option survive the invocation CI actually uses?** `pytest_addoption`
  in a nested conftest is not registered under every argument shape. Ran the pre-commit
  hook's own command (`cd cli && uv run python -m pytest -q`, which reaches
  `cli/tests/conftest.py` through `testpaths`) plus three other shapes; all accept the
  flag. Also proved the lag *bites* rather than merely parsing: one file goes from 0.52s
  to 15.5s at `--dispatch-lag=1.0`.
- **Round 3 — the documents.** Corrected a miscount (five instances of this shape have now
  been found, not four — three in PR #244 and two here) and a cross-reference to the new
  rule's heading. Re-ran the two fixed tests eight times unlagged: 8/8, and about 0.2s
  faster each, since a deleted `time.sleep` is time nobody spends again.
- **Critic review: not run — `reviews.critics` is empty in this repository**, so there is
  no second model configured to run one. Flagged on the PR rather than silently skipped.

## Capability docs

- [`docs/capabilities/testing-and-contracts.md`](../../capabilities/testing-and-contracts.md)
  — new *Asynchronous tests wait on the state they depend on (issue-251)* section stating
  the attempt/outcome rule, the sleep rule, the barrier preference and the
  `--dispatch-lag` obligation, plus a history row.

## Documentation

- [`skills/the-loop/reference/testing.md`](../../../skills/the-loop/reference/testing.md)
  — new *RULE: an asynchronous test waits on the state it depends on*, with the
  attempt/outcome table, the wrong/right pair, the three habits that follow, and how to
  find the shape by moving time. This is the surface that ships in the plugin, so the rule
  reaches every project the-loop works in.
- [`docs/contributing.md`](../../contributing.md) — *Hunting wait-ordering flakes*: the
  command, what it delays, and when to run it. This is where a contributor looks for "how
  do I run the tests", so it is where the flag belongs.
- [`docs/decisions/decision-089.md`](../../decisions/decision-089.md) + index row.
- **README.md and the guide: unchanged, deliberately.** Nothing here alters what the-loop
  *does* for a user — no command, no config key, no phase, no artifact. The one new
  affordance is a pytest flag for people working on this repository, which is what
  `contributing.md` is for.
