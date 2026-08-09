---
type: tasks
phase: tasks-breakdown
workItem: issue-185
status: approved
approvedBy: []
collaborators: [engineer]
riskTier: 4
overrides: {}
---

# Tasks: the contribution loop

> Phase 4. DAG: T1 → {T2, T3, T4} → T5 → T6 → {T7, T8} → T9. Each task's
> _Test:_ names a row of [testing-plan.md](testing-plan.md).

## Task list

- [x] **T1 — the graph.** Add `cli/the_loop/graph/pdlc-contribution-loop.yaml`
  (nodes, edges, skip sets per design), `PDLC_CONTRIBUTION_LOOP` in `model.py`,
  and the repo-override warning entry. _Requirements: R1, R4._ _Test: Unit (graph
  compiles/routes)._
- [x] **T2 — the goal gate.** New `graph/hooks/goal.py` (`post-goal-request`,
  `classify-goal`), registered in `hooks/__init__.py`; extend the runtime's decision
  recorder to persist the goal payload. _Requirements: R2._ _Test: Unit (goal parser),
  Security (unauthorized/self-authored)._
- [x] **T3 — the keyword.** `CONTRIBUTE` in `control.py` (command, default keyword,
  arming); dispatcher treats it as `start` at both spawn seams; cli-config schema
  gains `keywords.contribute`. _Requirements: R3._ _Test: Unit (keyword, arming),
  Security (ambiguity refusal)._
- [x] **T4 — durable loop choice.** `GraphState.loop` (write at `Runtime.start`,
  round-trip); `build_runtime(loop=…)`. _Requirements: R1.3._ _Test: Unit (state
  round-trip, migration)._
- [x] **T5 — loop resolution.** `GraphLink._outer_loop_name` (state-first, control
  record second, default third) wired into `_guarded`; same read in
  `core/graphs.py` verbs. _Requirements: R1.3, R3.1._ _Test: Unit (resolution order),
  Security (unknown name falls back)._
- [x] **T6 — integration walk.** Stubbed-integration test: goal-definition →
  phase-selection, authorized vs unauthorized goal, checklist from this graph.
  _Requirements: R2, R4.1._ _Test: Integration._
- [x] **T7 — plugin surface.** `commands/contribute-to.md`;
  `skills/the-loop/templates/contribution.md`. _Requirements: R4.2, R5._ _Test:
  Manual n/a — markdown lint only._
- [x] **T8 — docs.** SKILL.md, `reference/workflow.md`, README/guide "two loops"
  mentions, `docs/capabilities/process-graph.md` + `webhook-triggers.md`,
  `docs/config/cli/routing-options.md`, decision-070. _Requirements: all (the
  documentation gate)._ _Test: markdownlint._
- [x] **T9 — verification.** Execute the testing plan; record results + evidence.
  _Requirements: R5._ _Test: the plan itself._
