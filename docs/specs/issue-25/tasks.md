---
type: tasks
phase: tasks-breakdown
workItem: issue-25
status: approved
approvedBy: ["@MadaraUchiha-314 (PR #26 review: implement in this PR itself)"]
overrides: {}
---

# Tasks: specs organization and capability documentation

> Phase 3 of 3. Derived from the approved [`design.md`](design.md). Docs/config-only
> work item: the "test" for each task is the repo's own quality gates (markdownlint,
> schema validation, pre-commit parity) — no production code, so no red→green cycle.

## Task list

- [x] 1. Add `.the-loop/templates/capability.md` defining the capability-doc structure
  - Header, what-it-is, current behaviour (normative), design pointers, history table
  - _Depends on:_ none
  - _Requirements:_ R2.3, R6.1
  - _Test:_ `npx markdownlint-cli2 ".the-loop/templates/capability.md"`
- [x] 2. Add `workflow.capabilitiesDir` to the config contract
  - `config.schema.json` (new key, default `docs/capabilities`), `config.yaml`,
    `templates/config.yaml`
  - _Depends on:_ none
  - _Requirements:_ R6.2
  - _Test:_ `uv run python scripts/validate_config.py`
- [x] 3. Track the layer in `.the-loop/manifest.yaml`
  - Template entry + knowledge entries (`capabilities.md` index, `<capability>.md`
    records)
  - _Depends on:_ 1
  - _Requirements:_ R6.3
  - _Test:_ manifest lists both; markdownlint/pre-commit green
- [x] 4. Wire the rule and gate into the operating model
  - `skills/the-loop/SKILL.md` (principle + knowledge section),
    `skills/the-loop/reference/workflow.md` (fold-in step + ready-to-ship gate item),
    `README.md` (rules + repository layout)
  - _Depends on:_ 1, 2
  - _Requirements:_ R4, R5, R6.4
  - _Test:_ `npx markdownlint-cli2` over changed files
- [x] 5. Backfill `docs/capabilities/` from the existing specs
  - `capabilities.md` index + capability docs covering issue-1, issue-11, issue-12,
    issue-15, issue-17, issue-18, issue-21 and issue-25 (dogfood: this capability
    documents itself), each with history rows linking the specs/decisions
  - _Depends on:_ 1, 4
  - _Requirements:_ R1, R2, R3, R4, R7
  - _Test:_ `npx markdownlint-cli2 "docs/capabilities/*.md"`
- [x] 6. Record `docs/decisions/decision-020.md` + index row
  - Capability docs as the organized view of specs and single source of truth for
    current behaviour
  - _Depends on:_ 5
  - _Requirements:_ R2 (decision trail)
  - _Test:_ markdownlint green; decisions index links resolve
- [x] 7. Close out: execution log, phase label, evidence
  - Tick tasks here, update `execution-log.md` (phases, evidence), keep issue #25 label
    in sync, run the full gate suite
  - _Depends on:_ 1–6
  - _Requirements:_ all (evidence)
  - _Test:_ `pre-commit run --all-files` (exactly what CI runs)

## Dependency graph (DAG)

```
1 ─┬─→ 3
   ├─→ 4 ─→ 5 ─→ 6 ─→ 7
2 ─┘         ↑
        (1 also → 5)
```

## Checkpoints

- After task 2: `uv run python scripts/validate_config.py`.
- After task 5: markdownlint over `docs/capabilities/`.
- After task 7 (final): `pre-commit run --all-files` — recorded in the execution log as
  the validation evidence.
