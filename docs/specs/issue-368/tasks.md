---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#368"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Tasks: one rule for where a work item's attributes live

> The last spec artifact (requirements → design → testing plan → tasks). A DAG of
> implementation tasks derived from the approved design and testing plan.

## Task list

- [ ] 1. Declare the rule as data
  - `cli/the_loop/state.py`: an `ATTRIBUTES` table beside `GENERATED_PATHS` — one entry
    per top-level key of the three per-work-item files, with its kind (pointer, human
    decision, remote entity, operator ledger, machine handle, derived) and the file the
    rule allows it in
  - _Depends on:_ none
  - _Requirements:_ R1.1, R1.5, R6.1
  - _Test:_ T1 — `test_state_portability.py` (red→green)

- [ ] 2. `work-item-state.json` v2
  - `cli/the_loop/graph/state.py`: drop `session`; add `sessionPerPr`, `model`, `effort`
    and `pullRequests[]` (`ref`, `repository`, `number`, `url`, `stateDir`, `state`,
    `linkedAt`, `linkedBy`); `link_pr` idempotent by ref, `set_pr_state`; a v1 file's
    `session` is ignored on load and absent on the next save; `repository` validated
    through `repo_state_key`
  - _Depends on:_ 1
  - _Requirements:_ R2.1, R2.2, R3.1, R3.3, R4.1
  - _Test:_ T2, T3 (red→green)

- [ ] 3. `session: inherit` resolves through the session registry
  - `cli/the_loop/graph/runtime.py`: `resolve_session` asks the registry for the live
    endpoint of this state's ref (outer: the work item; inner: the PR) and falls back to
    `fresh-with-artifacts`; `cli/the_loop/graphlink.py`: `_bind_session` and `on_close`
    stop writing into the state file
  - _Depends on:_ 2
  - _Requirements:_ R3.1, R3.2, R3.3
  - _Test:_ T3, T4 (red→green)

- [ ] 4. The frozen choices move into the work item's file
  - `cli/the_loop/graph/hooks/selection.py`: the freeze writes `sessionPerPr`, `model`
    and `effort` into `WorkItemState` beside `skips`/`optIns`/`surface`; it stops
    emitting `frozenGraph`
  - `cli/the_loop/webhook/dispatcher.py`: `_tmux_for` and `_resolved_choice` read the
    state file in the checkout the session record names, falling back to the portable
    `graph` section for a work item frozen before this change, then to the operator's
    defaults; `_record_frozen_graph` is removed
  - _Depends on:_ 2
  - _Requirements:_ R4.1–R4.5, abuse cases 1–2
  - _Test:_ T9, T10 (red→green)

- [ ] 5. The portable record's sections
  - `cli/the_loop/workitem.py`: `SECTIONS` drops `GRAPH`, gains `CHANNELS` and
    `PULL_REQUESTS`; `owner_of(ref)` scans the pull-request maps; `index.json` lists one
    entry per work item naming its PR refs
  - `cli/the_loop/control.py`: `record_frozen_graph` removed, `frozen_graph` kept as the
    legacy reader only
  - _Depends on:_ 4
  - _Requirements:_ R4.2, R8.3, R10.1, R10.7
  - _Test:_ T11 (red→green)

- [ ] 6. One portable record per work item
  - `cli/the_loop/poller/poller.py`: `PollState` takes `(owner, ref)` — `owner == ref`
    writes `poll`, otherwise `pullRequests[ref]`; the owner is resolved before any write
    (session registry → portable maps → the router's linkage on the listed item), and a
    PR that resolves to nothing is a work item of its own
  - `cli/the_loop/webhook/dispatcher.py`: a PR with an owner records its upstream state
    through GraphLink and drops its nested ledger; **no** `ended` on a PR record
  - _Depends on:_ 5
  - _Requirements:_ R10.1–R10.6
  - _Test:_ T23, T6 (red→green)

- [ ] 7. The local record is a map of sessions keyed by ref
  - `cli/the_loop/sessions/registry.py`: `{workItem, channels?, sessions{ref → handles}}`;
    `record_owning` is a key lookup; `session_for`, `link_pull_request`, `save_endpoint`,
    `close_endpoint` and `touch` keep their signatures; a v1 record (top-level handles +
    `pullRequests[]`) loads into the map and is rewritten as v2; nothing about a pull
    request but its ref is kept
  - _Depends on:_ 1
  - _Requirements:_ R5.1, R5.2, R5.5, R8.1
  - _Test:_ T24, T12, T5 (red→green)

- [ ] 8. The channel binding is the operator's; the cursor is the machine's
  - `cli/the_loop/channels/state.py`: `threads` and `conversations` are no longer
    written, `cursors` keeps only `channel:*`; the old maps are exposed read-only as
    `legacy_bindings()`
  - `cli/the_loop/channels/slack.py`: `thread_for`/`bind` go through the portable
    record's `channels.slack`; `cursor`/`advance` through the work item's local record;
    the thread → work item index is built in memory from the portable records
  - _Depends on:_ 5, 7
  - _Requirements:_ R2.3, R5.1, R5.3, R5.4, R7.3, abuse case 6
  - _Test:_ T7, T8, T19 (red→green)

- [ ] 9. The control plane stops joining two identities
  - `cli/the_loop/core/*`, `cli/the_loop/api/routes.py`, `ui/`: the issue-302
    reconciliation is removed — one record per work item, its `pullRequests` keys are
    the nested rows; `nodes[]` comes from `the-loop check`
  - _Depends on:_ 6
  - _Requirements:_ R4.5, R10.1
  - _Test:_ T13, T22

- [ ] 10. Lifecycle: cleanup, reset, upgrade
  - `cli/the_loop/cleanup.py`, `reset.py`: cleanup deletes the local record (cursors with
    it) and keeps `channels`; reset clears every portable section including `channels`
    and `pullRequests`
  - `commands/upgrade-the-loop.md`: report the three retired locations and the per-PR
    portable records as no longer read; delete nothing
  - _Depends on:_ 6, 7, 8
  - _Requirements:_ R7.2, R8.1, R8.2, R10.6
  - _Test:_ T14, T23

- [ ] 11. The hand-off scenario
  - `cli/tests/test_state_root_integration.py`: the design's worked example on two state
    roots — the three pull requests and the thread survive; the new machine routes a PR
    event with no provider call
  - _Depends on:_ 6, 7, 8
  - _Requirements:_ R2.1–R2.3
  - _Test:_ T13 (red→green)

- [ ] 12. Docs, decision record and capability docs
  - `docs/cli/state.md` rewritten by the classification (attribute tables); the decision
    record superseding decision-046's file-level rule; capability docs `cli`,
    `process-graph`, `interactive-sessions`, `channels`, `control-plane`,
    `webhook-triggers`, `spec-workflow`
  - _Depends on:_ 9, 10
  - _Requirements:_ R9.1–R9.4
  - _Test:_ T15, T22

- [ ] 13. Verification
  - Execute the testing plan; record results, evidence and the security round
  - _Depends on:_ 11, 12
  - _Requirements:_ all
  - _Test:_ T22
