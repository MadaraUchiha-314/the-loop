---
type: tasks
phase: tasks-breakdown
workItem: ""
status: draft                # draft | in-review | approved
approvedBy: []
overrides: {}
---

<!-- Written per the `the-loop:writing` skill: front-load each section's
     conclusion, draw it rather than describe it (3+ named parts -> a mermaid
     diagram), and keep the formal registers formal (EARS, abuse cases,
     RFC-2119, API contracts, schema descriptions). No length limit — length
     follows the change; the test is whether a sentence can come out without
     losing information. A gated section stays even when it is empty. -->

# Tasks: <work item title>

> The last spec artifact (requirements → design → testing plan → tasks). A DAG of
> implementation tasks derived from the approved design and testing plan. MUST be
> reviewed/approved before implementation begins. Once approved, the-loop executes these
> end-to-end with minimal/no intervention.

## Task list

Each task is a checkbox, references the requirement(s) it satisfies, declares its
dependencies so the-loop can build the execution DAG, and names the **test(s) that will
prove it** — a row of `testing-plan.md`'s matrix, so the DAG and the plan cannot describe
different work. Keep tasks small and verifiable. TDD invariant (`tdd.mode`): **no production
code without a failing test that motivates it** — write/adjust the test first, watch it go
red, then make it green. **Security-relevant tasks** (they touch a trust boundary from
`design.md` §Security design) name the **negative test** proving the boundary holds —
abuse cases are tests like any other (`reference/security.md`).

- [ ] 1. <task summary>
  - Details / sub-steps
  - _Depends on:_ none
  - _Requirements:_ R1, R2
  - _Test:_ <testing-plan row + the test that proves this task, e.g. `T2 — pytest tests/test_x.py::test_y`> (red→green)
- [ ] 2. <task summary>
  - Details / sub-steps
  - _Depends on:_ 1
  - _Requirements:_ R1
  - _Test:_ <test command / case>
- [ ] 3. <task summary>
  - _Depends on:_ 1, 2
  - _Requirements:_ R3
  - _Test:_ <test command / case>

## Dependency graph (DAG)

A quick textual view of the order, e.g. `1 → 2 → 3` (or a mermaid graph).

## Checkpoints

At which task boundaries the-loop runs tests/validations and updates the execution log.
Record each task's test command and its **red→green** transition as evidence (`tdd.mode`).
After the last task, the **verification** node executes `testing-plan.md` — ticking each
activity and recording its command, outcome and committed evidence — and only then do the
review phases run the self/critic rounds AND the **security review gate**
(`security.review`, recorded in the execution log) before the work item can be marked
ready.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
