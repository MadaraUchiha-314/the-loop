---
type: tasks
phase: tasks-breakdown
workItem: issue-17
status: approved
approvedBy: ["@MadaraUchiha-314 (issue #17 as authored)"]
overrides: {}
---

# Tasks: a brainstorm phase and `/brainstorm` command

> Derived from the approved [`design.md`](design.md). Docs/plugin-content change — the
> "tests" are the config validator and markdownlint (see design → Testing strategy).

## Task list

- [x] 1. Add the `brainstorm.md` template (the root artifact)
  - New `.the-loop/templates/brainstorm.md` with front-matter + free-form sections.
  - _Depends on:_ none
  - _Requirements:_ R1
  - _Test:_ `markdownlint` passes on the new file
- [x] 2. Add the `/brainstorm` command
  - New `commands/brainstorm.md` — create/iterate/lock/convert flow.
  - _Depends on:_ 1
  - _Requirements:_ R2
  - _Test:_ `markdownlint` passes; command references the template + next step
- [x] 3. Wire `brainstorming` into config + manifest
  - `config.schema.json` (enum + default), `config.yaml`, `templates/config.yaml`,
    `manifest.yaml` (template + optional `spec-brainstorm` artifact).
  - _Depends on:_ 1
  - _Requirements:_ R1, R4
  - _Test:_ `python scripts/validate_config.py` exits 0
- [x] 4. Teach conversion + promotion
  - `new-requirement.md` derives from a locked sibling brainstorm; `create-ticket.md`
    carries `brainstorm.md` on promotion.
  - _Depends on:_ 1
  - _Requirements:_ R3
  - _Test:_ `markdownlint` passes; inspection of the two command files
- [x] 5. Generalize the iterate-until-locked rule in docs
  - Update `work-on.md`, `SKILL.md`, `reference/workflow.md`, `README.md` (chain, optional
    phase, state machine, the rule) + `decision-017.md` and the decisions index.
  - _Depends on:_ 1, 3
  - _Requirements:_ R4, R5
  - _Test:_ `markdownlint` passes on all changed docs
- [x] 6. Dogfood: write the issue-17 spec
  - `docs/specs/issue-17/{brainstorm,requirements,design,tasks,execution-log}.md`.
  - _Depends on:_ 1–5
  - _Requirements:_ R1–R5 (demonstration)
  - _Test:_ `markdownlint` passes; validator still green

## Dependency graph (DAG)

```
1 → 2
1 → 3 → 5
1 → 4
{1,3} → 5
{1..5} → 6
```

## Checkpoints

After task 3 and again after task 6: run `python scripts/validate_config.py` and
`pre-commit run --all-files` (ruff/pyright/markdownlint/schema) — record the outcome in
`execution-log.md`.
