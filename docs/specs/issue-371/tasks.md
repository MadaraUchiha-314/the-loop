---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#371"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: every comment the-loop finishes with says so on the comment

> The last spec artifact (requirements → design → testing plan → tasks). A DAG of
> implementation tasks derived from the approved design and testing plan.

## Task list

- [x] 1. The outcome → reaction table
  - `cli/the_loop/webhook/dispatcher.py`: `ACK_STATES`, built from the same
    `SETTLED_*` constants `SETTLED_OUTCOMES` is built from, mapping
    `control-executed → started·completed`, `control-rejected`/`control-ambiguous → error`
    and the suppressed family → `started`; scope refusals deliberately absent
  - _Depends on:_ none
  - _Requirements:_ R1.2, R1.3, R1.4
  - _Test:_ T1 (red→green)

- [x] 2. `_settle` acknowledges
  - `cli/the_loop/webhook/dispatcher.py`: `_settle` gains a keyword-only
    `acknowledge=True` and, after `deduper.mark_settled`, posts `ACK_STATES.get(outcome)`
    through the existing reactor; docstring states the record-then-decorate order and the
    never-raises contract it leans on
  - _Depends on:_ 1
  - _Requirements:_ R1.1, R2.1, R2.2, R2.5, R3.1
  - _Test:_ T2, T3, T4, T5, T6, T12 (red→green)

- [x] 3. The two sites that must stay silent
  - `cli/the_loop/webhook/dispatcher.py`: `_reject_control` gains `acknowledge=True` and
    passes it through to `_settle`; `_refuse_scope` calls it with `acknowledge=False`
    (issue-322 R2.6); `_dispatch_one`'s paused branch settles with `acknowledge=False`
    because the worker around it already reacted
  - _Depends on:_ 2
  - _Requirements:_ R2.3, R2.4
  - _Test:_ T7, T10 (red→green)

- [x] 4. The silent paths stay silent, the delivered branch stays as it was
  - `cli/tests/test_reactions_integration.py`: duplicate delivery, invented linkage and
    spawn-policy drop post nothing; `enabled: false` silences the new acknowledgements;
    issue-84's four existing scenarios pass unchanged
  - _Depends on:_ 3
  - _Requirements:_ R2.3, R2.5
  - _Test:_ T8, T9, T11

- [x] 5. Documentation
  - `docs/config/cli/routing-options.md`: reactions cover both branches, with R1.3's table
  - `docs/capabilities/webhook-triggers.md`: the acknowledgement rule and a history row
  - `evidence/documentation.md`: the capability docs reviewed, with the reason for each
    left unedited
  - _Depends on:_ 3
  - _Requirements:_ R5.1, R5.2
  - _Test:_ T14

- [x] 6. Gates
  - `make lint format-check typecheck` and the full suite green; `evidence/self-review.md`,
    `evidence/critic-review.md`, `evidence/security-review.md`,
    `evidence/final-validation.md`, `evidence/pull-requests.md`
  - _Depends on:_ 4, 5
  - _Requirements:_ all
  - _Test:_ T13, T15
