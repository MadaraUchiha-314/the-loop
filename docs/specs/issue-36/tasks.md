---
type: tasks
phase: tasks-breakdown
workItem: issue-36
status: approved
approvedBy: ["@MadaraUchiha-314"]
overrides: {}
---

# Tasks: templates become internal to the-loop

> Phase 3 of 3 (bugfix → design → tasks). Derived from the approved design.

## Task list

- [x] 1. Move `.the-loop/templates/` → `skills/the-loop/templates/`
  - `git mv` the whole directory so history is preserved.
  - _Depends on:_ none
  - _Requirements:_ R2
  - _Test:_ `test -d skills/the-loop/templates && ! test -d .the-loop/templates`
- [x] 2. Update the manifest
  - Remove the `templates:` per-project list; add `templatesDir` and a `deprecated`
    entry for `.the-loop/templates/`.
  - _Depends on:_ 1
  - _Requirements:_ R1, R3
  - _Test:_ inspection — `rg "templatesDir|deprecated" .the-loop/manifest.yaml`
- [x] 3. Stop `init` copying templates; teach `upgrade` to clean up
  - `init.md`: scaffold from the internal templates, drop the `.the-loop/templates/`
    creation line and repoint the authoritative-source pointer.
  - `upgrade-the-loop.md`: add the deprecated-path cleanup step + report group.
  - _Depends on:_ 2
  - _Requirements:_ R1, R3
  - _Test:_ inspection — `rg "skills/the-loop/templates|deprecated" commands/*.md`
- [x] 4. Repoint every reference to the internal location
  - Commands, `SKILL.md`, reference docs, README, architecture + capability docs.
  - _Depends on:_ 1
  - _Requirements:_ R4
  - _Test:_ `rg "\.the-loop/templates"` shows only intentional/historical references
- [x] 5. Update runtime consumers and config defaults
  - `dispatcher.py` default path constants + "kept in sync" comments.
  - `config.schema.json`, `.the-loop/config.yaml`, and the config template's
    `templatePath` / `promptTemplate` / `spawnPromptTemplate` defaults.
  - _Depends on:_ 1
  - _Requirements:_ R4
  - _Test:_ `pytest`, `ruff`, `pyright` green
- [x] 6. Add this spec + fold into capability/architecture docs
  - _Depends on:_ 3, 4, 5
  - _Requirements:_ R1–R4
  - _Test:_ `markdownlint` green; links resolve

## Dependency graph (DAG)

`1 → 2 → 3 → 6` and `1 → {4, 5} → 6`

## Checkpoints

After task 5, run the full local gate (`ruff`, `pyright`, `pytest`, `markdownlint`).
After task 6, verify `rg "\.the-loop/templates"` returns only the intended references.
