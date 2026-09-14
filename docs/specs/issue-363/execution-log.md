---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#363"
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: after a machine loss the daemon rewinds, replays and double-spawns

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-14 | — | **Risk tier 3**: the daemon's two ingress paths and the graph pointer. No sensitive path under `.the-loop/**` changes behaviour — the schema gains one additive key, mirrored byte-for-byte into the packaged copy — no auth or credential path is touched, and no new network call or write target is added. Three trust boundaries *move* and each is argued closed in [`bugfix.md`](bugfix.md) §Security considerations. Tier 3 waits for a human to approve the PR. `brainstorming` skipped — the reporter named the four code sites and the expected behaviour; `design-critic-review` not selected (`critics: []` in this repository, so a round would be `unavailable`). No authorized `the-loop execute` reaches this cloud session, so the selection is recorded here and every phase is walked by hand |
| requirements-definition | 2026-09-14 | pending — this branch's PR | [`bugfix.md`](bugfix.md) — six requirements, four abuse cases. Root cause confirmed by reading the four reads, not by trusting the ticket's summary of them |
| design | 2026-09-14 | pending — this branch's PR | [`design.md`](design.md) — one rule at four reads, [`decision-126`](../../decisions/decision-126.md) |
| test-planning | 2026-09-14 | pending — this branch's PR | [`testing-plan.md`](testing-plan.md) — eighteen rows, ten applicable; every `n/a` carries its reason |
| tasks-breakdown | 2026-09-14 | | [`tasks.md`](tasks.md) — ten tasks, red root first |
| implementation | 2026-09-14 | | On `claude/github-issue-363-yqyz3u`. TDD: [`evidence/red.md`](evidence/red.md) captured from a worktree of `HEAD` before any production change |
| verification | 2026-09-14 | | [`evidence/verification.md`](evidence/verification.md) — every applicable row plus `make check`; [`evidence/security-review.md`](evidence/security-review.md) — four abuse cases |
| needs-review | 2026-09-14 | | PR raised with the R10 briefing. Tier 3: the merge is the owner's |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#364](https://github.com/MadaraUchiha-314/the-loop/pull/364) | tasks 1–10: the whole work item | open |

## Progress entries

### 2026-09-14 — one defect, read four times

- **Phase:** requirements-definition → design
- **Did:** read each of the four sites the reporter named, rather than taking the ticket's
  account of them, and found that they are not four bugs. They are one rule applied four
  times: *absence of local state is read as absence of work.* The graph pointer, the
  comment ledger, the control record and the session's liveness probe each fail open to
  "nothing has happened here", and on a rebuilt machine that is false four times over.
  Framing it that way is what produced one small module and four guards rather than four
  independent patches.
- **Found, and it widened the fix inside the same diff:** the ticket's proposal 1 addresses
  `Runtime.start`. `start` is not the only rewind. `Runtime.advance` reads
  `state.current_node or self.graph.start`, so an *event* on a work item with no local state
  evaluates the start node too — and `phase-selection`'s exit chain will happily freeze a
  selection from a `the-loop execute` still sitting on the thread from four days ago. That
  is the actual mechanism behind the reporter's "13 `graph.frozen` + `graph.advanced`"
  within forty-two seconds: not thirteen spawns, thirteen *comments*. The guard therefore
  lives in `GraphLink._guarded` over both write actions, not in the two entry points, and
  `test_an_event_on_a_forgotten_item_does_not_advance_it_either` is the test that would have
  caught the narrower fix shipping.
- **Decided against the obvious fix, with the reason recorded:** adopting the node from the
  `loop:<phase>` label. A label names a phase, not a node, and carries nothing about which
  gates were approved, which phases were declared away, or which model was frozen — so
  adopting one fabricates four facts and makes a label an input that *places* a pointer.
  The label refuses; `the-loop graph force` places. See
  [decision-126](../../decisions/decision-126.md) §Alternatives rejected, which also records
  why the daemon does not commit-and-push the portable directory and why an issue work
  item's workspace does not start checking out a PR branch.
- **Next:** the red root.

### 2026-09-14 — red from a worktree, then four guards

- **Phase:** tasks-breakdown → implementation → verification
- **Did:** tasks 1–10. Wrote the twelve scenarios first and captured them failing against a
  `git worktree --detach HEAD` with only the test files copied in
  ([`evidence/red.md`](evidence/red.md)): eight fail, and the four that pass are the
  regression half — issue-119's pending start command, an unlabelled item entering its
  graph, a started item judged by its state file, and an unauthorized command still refused.
  Then `recovery.py`, `event_labels`, the portable `graph.position`, the `GraphLink`
  restore/refuse/publish, the poller's context-lost branch, the tmux grace window and its
  config key, and the spawn prompt's `$recovery_notice`.
- **The test suite was writing into this repository's own tracked state, and that stopped
  being cosmetic.** `test_graphlink_integration.py` and `test_graph_drive_integration.py`
  both built dispatchers with the default state layout — `.the-loop/portable`, *this*
  repository's records — so every run rewrote one of them in the checkout (the residue
  issue-339 flagged and issue-360's log re-flagged). Harmless while nothing read the records
  back. Once the graph position is published to them and restored from them, it is
  cross-test pollution: five graphlink tests failed with a work item standing at
  `requirements-approval` because a *different test* had published it there. Both files now
  take a `tmp_path` state root. This is the second time this residue has been noted and left;
  it is fixed here because this change made it load-bearing.
- **Nine respawn tests needed an honest fixture, not a weaker guard.** Every scenario in
  `test_tmux_runner_integration.py` that exercises the issue-80 respawn registers its
  session microseconds before the delivery — which is exactly the booting-session case the
  grace window now holds for, so the respawn path was no longer reached. The sessions are
  now registered with a `createdAt` an hour old, which is what a session whose harness
  *died* actually looks like. Weakening the window to keep the fixtures would have been
  fixing the test by breaking the feature.
- **Checkpoint/tests:** red first, then green. `make check`: 3642 passed, 1 skipped (3604
  before — thirty-eight added); ruff, ruff format, pyright, `validate_config` clean;
  markdownlint 0 errors over 1114 files.
- **Self-review, three passes.** Pass one found the refusal path in `on_spawn` still calling
  `_bind_session`, which writes a `graph-state.json` — so the *next* event would find a file,
  skip the guard, and rewind after all. The guard moved from the two entry points into
  `_guarded`, which also closed the `advance` hole above; the binding is simply not recorded
  for a work item whose pointer this machine does not hold. Pass two questioned the restore's
  placement: it was after `_outer_loop_name`, which is state-first, so a restored contribution
  item would have been addressed with the default graph. Moved ahead of it. Pass three checked
  the claim that `session_missing=False` is enough to get a retry rather than a respawn —
  `dispatcher.py:2423` keys the respawn on that flag alone and everything else falls through
  to the release path, so no dispatcher branch was needed; the integration scenario asserts
  the absence of `session.respawned`, `session.resume_failed` and `session.spawned` rather
  than the presence of the new error string.
- **Out of scope, noted for the owner:** `uv.lock` on `main` still records
  `the-loopy-one 16.0.0` against `cli/pyproject.toml`'s `16.0.1`, so any `uv run` rewrites one
  line and every contributor gets a dirty tree. Reverted here rather than carried into this
  diff, as issue-360 did — it is a release-process fix, not a machine-loss one.
- **Next:** the PR and its briefing.

## Verification results

> **Only when this work item declared `test-planning` away** (issue-179). This item kept
> the plan, so its results live in [`testing-plan.md`](testing-plan.md) §Verification
> results and this section stays as the template left it.

## Design critic review

> Not selected at `phase-selection` — this repository declares no critics
> (`critics: []`), so a round would be recorded `unavailable` and count for nothing. The
> section stays as the template left it.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop | new findings — the `_bind_session` hole that would have let the second event rewind, the restore ordering against `_outer_loop_name`, and the unverified retry claim; all three fixed | this log, entry 2 |
| 2 | self | the-loop | zero (converged) | this log, entry 2 |
| 3 | self | the-loop | zero (converged) | this log, entry 2 |
| 4 | critic | — | unavailable — no critic is configured in this repository (`critics: []`); does not count toward `reviews.criticReviewCount` | [`.the-loop/cli-config.yaml`](../../../.the-loop/cli-config.yaml) |
| 5 | security | built-in `security-review` skill | zero — no findings | [`evidence/security-review.md`](evidence/security-review.md) |

## Security review (gate)

- **Mechanism:** the harness's built-in `security-review` skill, run against
  `origin/main..HEAD` (see [`evidence/security-review.md`](evidence/security-review.md)).
- **Outcome:** pass — no findings. The four abuse cases of [`bugfix.md`](bugfix.md)
  §Security considerations each name a boundary this change *moves*, and each is argued and
  tested closed: a label can refuse but never place, a portable position writes only into a
  vacuum, the age rule only withholds, and the notice cannot echo a commenter's body.
- **Human sign-off:** n/a — risk tier 3, below the tier-4 threshold. The PR approval is the
  tier-3 gate.

## Final validation evidence

| Acceptance criterion | Proof |
|---|---|
| R1.1 — no rewind of a labelled item with no local state | `test_a_forgotten_item_is_not_rewound_and_still_gets_a_session`, `test_an_event_on_a_forgotten_item_does_not_advance_it_either` (T5) |
| R1.2 — the spawn still happens | the `waits is False` assertion in the same scenario (T5) |
| R1.3 — an unlabelled item is unaffected | `test_an_item_with_no_phase_label_still_enters_the_graph` (T7) |
| R1.4 — the remedy is named, never taken | `test_the_notice_names_the_operators_remedy_and_claims_no_rewind` (T1); `graph.rewind_refused` carries no action |
| R2.1 — the position is published beside the selection | `test_the_position_is_published_on_every_graph_write`, `test_recording_a_position_keeps_the_frozen_selection` (T2, T6) |
| R2.2 / R2.3 — restored, verbatim | `test_a_published_position_is_restored_byte_for_byte` (T6) |
| R3.1 — the thread is baselined, commands included | `test_a_forgotten_items_old_commands_are_baselined_and_announced_once` (T5) |
| R3.2 — issue-119 intact | `test_a_new_items_pending_start_command_is_still_forwarded` (T7) |
| R3.3 — one notice, naming the cutoff | the same scenario's `len(posts.bodies) == 1` (T5) |
| R4.1 / R4.2 / R4.3 — the grace window, both sides and off | `test_a_session_still_inside_its_grace_window_is_not_reported_missing`, `…_past_its_grace_window_…`, `…_a_zero_grace_window_…`, `test_a_comment_arriving_during_the_boot_does_not_spawn_a_second_session` (T3, T8) |
| R5.1 / R5.2 — the recovery notice, and its absence | `test_a_recovery_spawn_prompt_says_the_conversation_is_gone`, `test_an_ordinary_spawn_gets_nothing` (T9) |
| R6.1 — red before, green after | [`evidence/red.md`](evidence/red.md) → [`evidence/verification.md`](evidence/verification.md) |

`make check` green on the final tree: 3642 passed, 1 skipped; 0 type errors; 0 markdown
errors. Full transcript in [`evidence/verification.md`](evidence/verification.md).

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [process-graph.md](../../capabilities/process-graph.md) | A new §*Surviving a machine that has forgotten the work item*: the pointer only moves forward, a label may refuse but never place, the position travels on the portable record, and a restore writes only into a vacuum | `issue-363`, linking this spec and [decision-126](../../decisions/decision-126.md) |
| [webhook-triggers.md](../../capabilities/webhook-triggers.md) | A new §*A first sight of a work item the-loop has already worked*: a control command is executed once ever, the withholding is announced once, the age rule only withholds, and a re-adoption spawn is told its conversation is gone | `issue-363`, same links |
| [interactive-sessions.md](../../capabilities/interactive-sessions.md) | §Current behaviour gains the spawn grace window — a pane that does not answer inside `spawnGraceSeconds` of the record's `createdAt` is a transient failure, not a missing session | `issue-363`, same links |

No other capability doc changed. [cli.md](../../capabilities/cli.md) describes
`the-loop graph force` as the audited escape hatch that moves a pointer regardless of
gates, which is exactly what it still is and exactly what the refusal points a human at —
the verb's contract is unchanged, only how often an operator meets it.

## Documentation

| Document | What changed |
|----------|--------------|
| [decision-126](../../decisions/decision-126.md) | New. Why a forgotten work item is refused rather than restarted, and the five alternatives rejected — adopting the node from the label, a daemon that pushes the portable directory, a workspace that checks out a PR branch for an issue item, conditioning the no-replay rule on a zero-session daemon start, and coalescing the poll cycle |
| [decisions.md](../../decisions/decisions.md) | The index row for decision-126 |
| [routing-options.md](../../config/cli/routing-options.md) | `tmux.spawnGraceSeconds` — type, default, what it measures from, and what `0` restores |
| [cli-config.yaml](../../../.the-loop/cli-config.yaml) + [the shipped template](../../../skills/the-loop/templates/cli-config.yaml) | The new key with its commented reason |
| [webhook-autoexecute-prompt.md](../../../skills/the-loop/templates/webhook-autoexecute-prompt.md) | A `$recovery_notice` placeholder, mirrored byte-for-byte in `DEFAULT_SPAWN_TEMPLATE` |

No page under `docs/cli/` changed: no command's contract moved. `README.md` and the skill's
`reference/` describe the loop a *work item* walks, not how a daemon re-adopts one after its
host is rebuilt — that is operator behaviour, and it is documented where operators look, in
the two capability docs and the routing options page above.
