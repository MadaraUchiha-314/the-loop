---
type: tasks
phase: tasks-breakdown
workItem: issue-12
status: approved
approvedBy: ["@MadaraUchiha-314 (issue author intent)"]
overrides: {}
---

# Tasks: the-loop should be compatible with Cursor

> Phase 3 of 3. DAG of implementation tasks derived from the approved design.

## Task list

- [x] 1. Research Cursor's plugin equivalent
  - Cursor 2.4 Agent Skills (SKILL.md standard), Cursor 2.5 plugins
    (`.cursor-plugin/plugin.json` + `marketplace.json`, auto-discovered `skills/`,
    `commands/`, `rules/`, `agents/`, `hooks/`), hook event model vs Claude's.
  - _Depends on:_ none
  - _Requirements:_ R1
  - _Test:_ findings recorded in `decision-015` (review-verified)
- [x] 2. Cursor manifests
  - `.cursor-plugin/plugin.json` (explicit `skills/`/`commands/`/`rules/` paths, no
    `hooks`) and `.cursor-plugin/marketplace.json`, mirroring the `.claude-plugin/`
    pair.
  - _Depends on:_ 1
  - _Requirements:_ R2
  - _Test:_ CI JSON parse step includes both files
- [x] 3. Session-reminder rule
  - `rules/the-loop.mdc` (alwaysApply), guarded on `.the-loop/config.yaml`; note in
    `hooks/hooks.json` description that Cursor parity comes from the rule.
  - _Depends on:_ 1
  - _Requirements:_ R3
  - _Test:_ `uv run python -c "import json; json.load(open('hooks/hooks.json'))"`
- [x] 4. Harness-neutral command prose
  - Annotate `${CLAUDE_PLUGIN_ROOT}` references in `init`, `upgrade-the-loop`,
    `create-design`, `create-tasks-plan`, `new-requirement` to cover Cursor.
  - _Depends on:_ 1
  - _Requirements:_ R2
  - _Test:_ `npx markdownlint-cli2 "**/*.md"`
- [x] 5. Docs + decision record
  - README (install/layout/commands note), skill + `automation.md` + `workflow.md`,
    `architecture.md`, `roadmap.md` (resolve the open question), `decision-015` +
    index, this 3-phase spec + execution log.
  - _Depends on:_ 2, 3, 4
  - _Requirements:_ R1, R4
  - _Test:_ `npx markdownlint-cli2 "**/*.md"`

## Dependency graph (DAG)

`1 → {2, 3, 4} → 5` (research gates everything; docs land last).

## Checkpoints

After tasks 4 and 5: `make check` (ruff · pyright · schema validation · pytest ·
markdownlint) — the same command CI runs.
