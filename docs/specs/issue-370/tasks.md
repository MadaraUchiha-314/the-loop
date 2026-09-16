---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#370"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: a pull request is tracked because the-loop recorded it

> The last spec artifact (requirements → design → testing plan → tasks). A DAG of
> implementation tasks derived from the approved design and testing plan.

## Task list

- [ ] 1. The poller stops inferring a pull request's owner
  - `cli/the_loop/poller/poller.py`: `_resolve_owner` drops the third question (the
    router's linkage on the listed item); the docstring states the two recorded sources
    and the "it is the work item" default
  - _Depends on:_ none
  - _Requirements:_ R1.1, R1.2
  - _Test:_ T1, T2 (red→green)

- [ ] 2. Delivery routing proven untouched
  - `cli/tests/test_poller_integration.py`: a Gherkin-docstring scenario that a comment on
    an inferred-linkage pull request still reaches the work item's session
  - _Depends on:_ 1
  - _Requirements:_ R1.3
  - _Test:_ T3

- [ ] 3. `work-item-state.json` gets one writer
  - `cli/the_loop/graphlink.py`: `on_pr_linked` loses `linked_by` and always records
    `"session"`
  - `cli/the_loop/webhook/dispatcher.py`: `_record_pr_binding` writes the registry
    endpoint only
  - `cli/the_loop/graph/state.py`: `link_pr` defaults to `"session"`; `PR_LINKED_BY`
    documented as the **read** vocabulary that keeps `"event"` for files written before
    this change
  - _Depends on:_ none
  - _Requirements:_ R2.1, R2.2, R2.3
  - _Test:_ T4, T5, T6 (red→green)

- [ ] 4. the-loop stops asking GitHub which pull requests relate to a work item
  - `cli/the_loop/graph/integrations/github.py`: remove `linked-pulls` from `OPERATIONS`,
    both transports and the GraphQL query constant
  - _Depends on:_ none
  - _Requirements:_ R3.1
  - _Test:_ T7 (red→green)

- [ ] 5. The review brief pre-fills from what the-loop recorded
  - `cli/the_loop/graph/hooks/review.py`: `_detected_pulls` reads `work-item-state.json`'s
    `pullRequests[]` then `pr-loops/`, deduplicated; the provider call is gone and the
    module docstring says what the two sources are
  - _Depends on:_ 4
  - _Requirements:_ R3.2, R3.3
  - _Test:_ T8 (red→green)

- [ ] 6. The link is recorded by a hook, not by the model
  - `hooks/the-loop-link-pr.py`: new stdlib-only `PostToolUse` wrapper — extract the pull
    request from the tool **response** (`gh pr create` URL, MCP `create_pull_request`),
    resolve the work item (`THE_LOOP_WORK_ITEM` → registry by harness session id →
    registry by cwd), run `the-loop sessions link-pr`, always exit 0
  - `hooks/hooks.json`: the `PostToolUse` entry and its matcher
  - _Depends on:_ none
  - _Requirements:_ R4.1, R4.2, R4.3, R4.4
  - _Test:_ T9, T10, T11, T13, T15 (red→green)

- [ ] 7. A spawned session knows its work item
  - `cli/the_loop/runner.py`: `WORK_ITEM_ENV_VAR`, injected through `new-session -e`
    beside `THE_LOOP_INSTANCE`, behind the same tmux-version probe, for every spawn that
    has a work item
  - _Depends on:_ none
  - _Requirements:_ R5.1, R5.2
  - _Test:_ T12 (red→green)

- [ ] 8. Documentation
  - `docs/capabilities/webhook-triggers.md`, `docs/capabilities/process-graph.md`,
    `docs/capabilities/cli.md`, `docs/capabilities/review-loop.md`: the new rule, with a
    history row per doc
  - `skills/the-loop/reference/automation.md`: the hook is the primary path, the command
    is the fallback
  - `docs/decisions/decision-1xx.md`: the tracking/delivery split this work item rules on
  - _Depends on:_ 1, 3, 4, 5, 6, 7
  - _Requirements:_ R6.1, R6.2
  - _Test:_ T14

- [ ] 9. Gates
  - `make lint format-check typecheck` and the full suite; evidence under
    `docs/specs/issue-370/evidence/` (self-review, critic-review, security-review,
    documentation, final-validation, pull-requests)
  - _Depends on:_ 1–8
  - _Requirements:_ all
  - _Test:_ T1–T15
