---
type: tasks
phase: tasks-breakdown
workItem: issue-1
status: approved
approvedBy: ["@MadaraUchiha-314 (issue author intent)"]
overrides: {}
---

# Tasks: The Loop — bootstrap the-loop

> Phase 3. DAG of tasks for the v0 bootstrap. All complete; retained as the record and
> as a worked example of `tasks.md`.

## Task list

- [x] 1. Plugin distribution: `plugin.json`, `marketplace.json`
  - _Depends on:_ none
  - _Requirements:_ R1
- [x] 2. Project footprint: `config.schema.json`, default `config.yaml`, `manifest.yaml`,
       `external-tools.md`, `collaborators.yaml`
  - _Depends on:_ none
  - _Requirements:_ R2, R4
- [x] 3. Templates: epic/story/bug + requirements/bugfix/design/tasks/execution-log/
       decision/learning
  - _Depends on:_ 2
  - _Requirements:_ R2, R3
- [x] 4. Commands: `init`, `work-on` (3-phase), `upgrade-the-loop`
  - _Depends on:_ 2, 3
  - _Requirements:_ R1, R3
- [x] 5. Operating model: `the-loop` skill + SessionStart hook
  - _Depends on:_ 2
  - _Requirements:_ R1, R3
- [x] 6. Knowledge: architecture index, decisions 001–004, learnings 001
  - _Depends on:_ none
  - _Requirements:_ R4
- [x] 7. Self-referential spec + execution log for issue #1 under `docs/specs/issue-1/`
  - _Depends on:_ 3
  - _Requirements:_ R3, R4
- [x] 8. README with install/usage/roadmap
  - _Depends on:_ 1, 4
  - _Requirements:_ R1
- [x] 9. Validate (JSON parses, configs validate against schema, tree matches manifest);
       commit; push
  - _Depends on:_ 1, 2, 3, 4, 5, 6, 7, 8
  - _Requirements:_ R1, R2, R4

## Dependency graph (DAG)
`{1,2,6} → 3 → {4,5,7} → 8 → 9` (2 also feeds 4/5; 1 also feeds 8).

## Checkpoints
- After task 9: run JSON + schema validation and the manifest tree check (see
  execution-log).
