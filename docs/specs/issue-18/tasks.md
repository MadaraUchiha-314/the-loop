---
type: tasks
phase: tasks-breakdown
workItem: issue-18
status: approved
approvedBy: ["@MadaraUchiha-314 (issue #18 as authored)"]
overrides: {}
---

# Tasks: UI/UX design artifacts in the design phase

> Derived from the approved [`design.md`](design.md). Docs/plugin-content change — the
> "tests" are the config validator and markdownlint (see design → Testing strategy).

## Task list

- [x] 1. Add `design.uiArtifacts` config
  - `config.schema.json` (new `design` section), `config.yaml`, `templates/config.yaml`.
  - _Depends on:_ none
  - _Requirements:_ R2
  - _Test:_ `python scripts/validate_config.py` exits 0
- [x] 2. Track the `design/` artifact in the manifest
  - New optional `spec-design-artifacts` work-item artifact (phase `design`).
  - _Depends on:_ none
  - _Requirements:_ R1
  - _Test:_ `markdownlint`/inspection; validator green
- [x] 3. Add the UI/UX design section to the design template
  - `.the-loop/templates/design.md` — inventory table + flows/tokens/a11y/evidence.
  - _Depends on:_ 1
  - _Requirements:_ R1
  - _Test:_ `markdownlint` passes on the template
- [x] 4. Write the `design-artifacts.md` reference (the designer iteration loop)
  - New `skills/the-loop/reference/design-artifacts.md`; self-contained rule; Figma↔code;
    evidence & hand-off.
  - _Depends on:_ none
  - _Requirements:_ R3, R4
  - _Test:_ `markdownlint` passes
- [x] 5. Wire commands + skill + README
  - `create-design.md`, `work-on.md`, `SKILL.md`, `reference/workflow.md`,
    `reference/collaboration.md`, `README.md` reference the convention and the new doc.
  - _Depends on:_ 3, 4
  - _Requirements:_ R5
  - _Test:_ `markdownlint` passes on all changed docs
- [x] 6. Record the decision
  - `docs/decisions/decision-018.md` + decisions index.
  - _Depends on:_ 1–5
  - _Requirements:_ R1–R5 (rationale)
  - _Test:_ `markdownlint` passes
- [x] 7. Dogfood: write the issue-18 spec + illustrative artifact
  - `docs/specs/issue-18/{requirements,design,tasks,execution-log}.md` and a
    self-contained `design/design-phase-artifacts.html`.
  - _Depends on:_ 1–6
  - _Requirements:_ R1–R5 (demonstration)
  - _Test:_ `markdownlint` passes; validator still green; the HTML has no external deps

## Dependency graph (DAG)

```
1 → 3 → 5
4 → 5
{1,3,4,5} → 6 → 7
2 → 7
```

## Checkpoints

After task 1 and again after task 7: run `python scripts/validate_config.py` and
`pre-commit run --all-files` (ruff/pyright/markdownlint/schema) — record the outcome in
`execution-log.md`.
