---
type: tasks
phase: tasks-breakdown
workItem: issue-11
status: approved
approvedBy: ["@MadaraUchiha-314 (issue author intent)"]
overrides: {}
---

# Tasks: Integration tests and OpenAPI specs

> Phase 3 of 3. DAG of implementation tasks derived from the approved design.

## Task list

- [x] 1. Scenario extraction library (`the_loop/scenarios`)
  - Line-based Gherkin extraction with comment-marker stripping; `Scenario` dataclass;
    `collect_scenarios` over globs; built-in default globs.
  - _Depends on:_ none
  - _Requirements:_ R1, R2
  - _Test:_ `pytest cli/tests/test_cli.py -k extract or collect` (red→green)
- [x] 2. `the-loop scenarios` command
  - Register the command; glob resolution (`--glob` > config > defaults);
    table/markdown/json renderers; fixture integration test following the convention.
  - _Depends on:_ 1
  - _Requirements:_ R2
  - _Test:_ `pytest cli/tests/test_cli.py -k scenarios_command` (red→green)
- [x] 3. Config contract: `testing` + `apiSpecs`
  - Extend `config.schema.json`; mirror in `templates/config.yaml` and the repo's own
    `config.yaml`; track `specs/openapi/` + `specs/graphql/` patterns in the manifest.
  - _Depends on:_ none
  - _Requirements:_ R1, R3, R4
  - _Test:_ `uv run python scripts/validate_config.py`
- [x] 4. Codify conventions in the skill
  - New `reference/testing.md`; wire into `SKILL.md` (reference list, operating
    principles, config sections), `reference/tooling.md`, the design template, READMEs.
  - _Depends on:_ 3
  - _Requirements:_ R1, R3, R4
  - _Test:_ `npx markdownlint-cli2 "**/*.md"`
- [x] 5. Decision record + spec artifacts
  - `decision-014` (incl. the GraphQL-TODO resolution) + this 3-phase spec + execution
    log.
  - _Depends on:_ 4
  - _Requirements:_ R4
  - _Test:_ `npx markdownlint-cli2 "**/*.md"`

## Dependency graph (DAG)

`1 → 2`; `3 → 4 → 5` (the two chains are independent until 4 references 1–3).

## Checkpoints

After tasks 2, 3 and 5: `make check` (ruff · pyright · schema validation · pytest ·
markdownlint) — the same command CI runs.
