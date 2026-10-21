---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#514"
status: draft
approvedBy: []
overrides: {}
---

<!-- Written per the `the-loop:writing` skill. -->

# Tasks: split `/the-loop:init` into `/init`, `/init-cli` and `/init-gateway`

> The `tasks-breakdown` node was skipped at phase-selection, so this list is
> [`design.md`](design.md) § Implementation order turned into checkboxes. The
> `implementation` node's exit checks those boxes. The design (locked at `design-approval`)
> stays the source; `testing-plan.md` was skipped as well, so each `_Test:_` names a check
> from design § Testing strategy.

## Task list

- [x] 1. Tests first (red)
  - New `cli/tests/test_init_commands.py` with the three scenarios from design § Testing
    strategy:
    - every command is listed in the command reference and the skill;
    - `/init` sets up no daemon;
    - each init command offers both modes.
  - In `cli/tests/test_migrations.py`, the two Jira assertions expect `/the-loop:init-cli`.
  - _Depends on:_ none
  - _Requirements:_ R1.2, R1.3, R2.1, R3.1, R4.1, R5.1
  - _Test:_ `uv run pytest cli/tests/test_init_commands.py cli/tests/test_migrations.py`.
    Red before task 2.
- [x] 2. The three command files
  - Rewrite `commands/init.md` (repository only, hand-off paragraph).
  - Add `commands/init-cli.md` and `commands/init-gateway.md`, with each of today's steps
    carried to the owner design's mapping table names.
  - _Depends on:_ 1
  - _Requirements:_ R1, R2, R3, R4
  - _Test:_ the `test_init_commands.py` scenarios turn green.
- [x] 3. Onboarding reference and skill
  - `skills/the-loop/reference/onboarding.md`: reorganise by config file and command.
  - `SKILL.md`: § Commands and the reference-list line.
  - _Depends on:_ 2
  - _Requirements:_ R5.1
  - _Test:_ the "listed in the skill" scenario; markdownlint.
- [x] 4. Strings outside the prose
  - `cli/the_loop/migrations.py`: the two Jira messages.
  - `.the-loop/manifest.yaml`: the two comments.
  - Both copies of `cli-config.schema.json`: the `x-onboarding.description` string only.
  - _Depends on:_ 1
  - _Requirements:_ R5.2; design § Trade-offs
  - _Test:_ `test_migrations.py` turns green; `test_onboarding_schema.py`,
    `test_manifest_schemas.py` and the schema parity checks stay green.
- [x] 5. User docs, capability doc, decision
  - The docs the design's _Other edits_ table lists: guides, the command reference, the
    config docs, the operating-model index, `upgrade-the-loop.md`.
  - `docs/capabilities/distribution.md` with an issue-514 history row.
  - `docs/decisions/decision-149.md` plus its index row.
  - _Depends on:_ 2, 3
  - _Requirements:_ R5.1, R5.3, R5.4
  - _Test:_ the "listed in the command reference" scenario; markdownlint; the docs-parity
    tests.
- [x] 6. Checkpoint: the full suite
  - Run pre-commit: ruff, pyright, pytest, markdownlint, config validation.
  - _Depends on:_ 1–5
  - _Requirements:_ all
  - _Test:_ `uv run pre-commit run --all-files` green.

## Dependency graph (DAG)

`1 → 2 → 3 → 5 → 6`, and `1 → 4 → 6`.

## Checkpoints

- **After task 2:** the new test file is green.
- **After task 4:** the migrations and schema tests are green.
- **Task 6:** the full suite.
- **Verification:** the dry-run walkthroughs of design § Testing strategy, committed as
  `evidence/dry-runs.md`.
