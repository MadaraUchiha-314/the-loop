---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#253"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Tasks: one owner per work item, one session per working tree

> The last spec artifact. A DAG derived from the design and testing plan.

## Task list

- [x] 1. Write the failing tests for the ownership rule
  - A same-repository pull request event delivers into the work item's session, spawns
    nothing, and is still recorded on the record with an empty `tmuxTarget`.
  - A same-repository pull request that **already** has an endpoint session stops being
    fed, with nothing torn down.
  - _Depends on:_ none
  - _Requirements:_ R1.1, R1.2, R1.3
  - _Test:_ `T1`, `T10 — pytest cli/tests/test_routing.py` (red→green)

- [x] 2. Write the failing tests for "a checkout, or no session"
  - A cross-repository pull request with no workspace is declined, its event delivered
    into the work item's session, and its binding still recorded.
  - A cross-repository pull request with a workspace spawns in a worktree of **that**
    repository, keyed on its own slug and at a different path from the record's.
  - _Depends on:_ none
  - _Requirements:_ R2.1, R2.2, R2.4
  - _Test:_ `T8 — pytest cli/tests/test_routing.py -k cross_repo`,
    `T4 — pytest cli/tests/test_workspace.py` (red→green)

- [x] 3. Capture the red run as evidence
  - _Depends on:_ 1, 2
  - _Requirements:_ R3.1
  - _Test:_ `evidence/red.md`

- [x] 4. `_same_repository`, and the rule in `_endpoint_for`
  - One module-level helper comparing `(provider, path)`; the rule placed **before**
    `record.endpoint_for(pr)` so an existing endpoint session is bypassed too.
  - _Depends on:_ 3
  - _Requirements:_ R1.1, R1.2
  - _Test:_ `T1`, `T10` (green)

- [x] 5. `_endpoint_cwd`, and the spawn seam that uses it
  - `Optional[str]`; `None` is the refusal. Workspace-prepared checkout keyed on the pull
    request's slug; `WorkspaceError` caught and turned into a refusal rather than a raise.
    `endpoint.cwd` records the checkout actually used; `graphlink.on_pr_spawn` keeps
    `record.cwd` (the spec chain's home, not the session's).
  - _Depends on:_ 3
  - _Requirements:_ R2.1, R2.2, R2.3
  - _Test:_ `T4`, `T8` (green)

- [x] 5a. Self-review finding: enforce the invariant, do not infer it
  - `_prepare_workspace` falls back to `spawnWorkdir` for a payload naming no repository,
    which can resolve to the record's own tree — so the design's claim ("two harness
    conversations never share a working tree") held by inference from the workspace layout
    rather than by a check. `_same_path` + a `shared-worktree` refusal now enforce it,
    with a test driving the guard through the real spawn seam.
  - _Depends on:_ 5
  - _Requirements:_ R2.2, R2.4
  - _Test:_ `T8 — pytest cli/tests/test_routing.py -k lands_on_the_records_tree` (red→green)

- [x] 6. `session.pr_session_declined` in the event catalogue
  - Named reasons `no-separate-checkout` / `workspace-failed`; `session.pr_spawned`'s
    description amended to say it is now reached only from another repository.
  - _Depends on:_ 5
  - _Requirements:_ R2.4
  - _Test:_ `T12 — pytest cli/tests/test_eventlog.py` (the catalogue-drift check)

- [x] 7. Rewrite the two integration scenarios the behaviour change invalidates
  - `test_pr_comment_reaches_the_linked_issues_work_item` and
    `test_pr_event_still_reaches_its_work_item_after_the_link_is_removed`, Gherkin
    included — the second still proves issue-172's durable binding, now by showing the
    event reaches the **work item** off the binding alone.
  - _Depends on:_ 4, 5
  - _Requirements:_ R1.1, R1.3, R1.4
  - _Test:_ `T2` (green)

- [x] 8. Run the full suite and the repo's own gates
  - _Depends on:_ 4, 5, 6, 7
  - _Requirements:_ R3.1
  - _Test:_ `T12`, `T13`

- [x] 9. Capability docs and the config reference
  - `docs/capabilities/webhook-triggers.md` (the `sessionPerPr` clause and a changelog
    row), `docs/config/cli/routing-options.md` (`tmux.sessionPerPr`),
    `docs/capabilities/capabilities.md` if the index states the old shape.
  - _Depends on:_ 8
  - _Requirements:_ R1, R2
  - _Test:_ `T12 — pytest cli/tests/test_docs_parity.py`

- [x] 10. Decision record and CHANGELOG
  - `decision-088` refining `decision-064` D3, indexed in `decisions.md`.
  - _Depends on:_ 9
  - _Requirements:_ R1, R2
  - _Test:_ `T13`
