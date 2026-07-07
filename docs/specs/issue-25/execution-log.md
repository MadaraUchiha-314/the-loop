---
type: execution-log
workItem: issue-25
phase: needs-review
status: in-progress
---

# Execution Log: specs organization and capability documentation

> Append-only progress log for issue-25. The-loop keeps the ticket's phase label in sync
> with the `phase` front-matter above.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| brainstorming | 2026-07-06 | @MadaraUchiha-314 (PR #26 review) | Root artifact drafted; all five open questions answered in PR #26 review and folded back; brainstorm locked |
| requirements-definition | 2026-07-07 | @MadaraUchiha-314 (PR #26: "implement in this PR itself") | Derived from the locked brainstorm; no open questions |
| design | 2026-07-07 | @MadaraUchiha-314 (PR #26: "implement in this PR itself") | Docs/config-only; no runtime code |
| tasks-breakdown | 2026-07-07 | @MadaraUchiha-314 (PR #26: "implement in this PR itself") | 7-task DAG |
| implementation | 2026-07-07 |  | Template, config key, manifest, skill/workflow/README wiring, backfill, decision-020 |
| needs-review | 2026-07-07 |  | Implemented in PR #26 per reviewer direction; awaiting human review |
| complete |  |  |  |

## Progress entries

### 2026-07-06 — draft the root brainstorm artifact

- **Phase:** brainstorming
- **Did:**
  - Authored `docs/specs/issue-25/brainstorm.md` exploring how the-loop should
    organize specs: the raw (per-work-item) vs organized (per-capability) split, four
    candidate options with pros/cons, and a working hypothesis (living capability docs
    as the organized view, folded in per work item and gated in the ready-to-ship
    checklist).
  - Raised the five open questions (location, taxonomy ownership, normativity, fold-in
    timing, migration) for human feedback via the PR and issue #25.
- **Checkpoint/tests:** `pre-commit run --all-files` (markdownlint, schema validation)
  — see the PR checks.
- **Next:** iterate the brainstorm with feedback until locked (`status: approved`),
  then derive `requirements.md` from it.
- **Blockers:** open questions 1–5 in `brainstorm.md` need human answers.

### 2026-07-07 — fold review answers back in; lock the brainstorm

- **Phase:** brainstorming
- **Did:** @MadaraUchiha-314 answered all five open questions in PR #26 review:
  `docs/capabilities/` as the organized layer; taxonomy both product-feature and
  architecture shaped, established via PR-review feedback; capability docs are the
  **single source of truth** for current behaviour; fold-in happens in the **same PR**
  (ready-to-ship gate); **backfill** existing specs. Folded the answers into
  `brainstorm.md` (§ Open questions resolved, leaning confirmed, hand-off updated) and
  locked it (`status: approved`).
- **Checkpoint/tests:** markdownlint via pre-commit — green.
- **Next:** derive `requirements.md` from the locked brainstorm
  (requirements-definition phase) once this PR merges.
- **Blockers:** none.

### 2026-07-07 — implement the capability-docs layer (in PR #26, per reviewer)

- **Phase:** requirements-definition → design → tasks-breakdown → implementation →
  needs-review
- **Did:**
  - Derived `requirements.md` (R1–R7), `design.md` and the 7-task `tasks.md` DAG from
    the locked brainstorm (reviewer approved proceeding in-PR: "implement in this PR
    itself").
  - Added `.the-loop/templates/capability.md`; added `workflow.capabilitiesDir` to
    `config.schema.json`, `config.yaml`, `templates/config.yaml`; tracked the template
    and knowledge files in `manifest.yaml`.
  - Wired the fold-in rule and the new ready-to-ship gate item into `SKILL.md`,
    `reference/workflow.md` and `README.md`; noted the layer in
    `docs/architecture/architecture.md`.
  - Backfilled `docs/capabilities/`: `capabilities.md` index + 8 capability docs
    (spec-workflow, capability-docs, distribution, cli, webhook-triggers,
    testing-and-contracts, design-artifacts, release-publishing) with history rows
    covering issues 1, 11, 12, 15, 17, 18, 21 and 25.
  - Recorded `docs/decisions/decision-020.md` + index row; ticked all 7 tasks.
  - Capability docs affected by this work item: `capability-docs.md` (new, dogfooded)
    and `spec-workflow.md` (gate change) — fold-in done in this PR.
- **Checkpoint/tests:** `uv run python scripts/validate_config.py` → both configs
  VALID; `pre-commit run --all-files` → all hooks green (see final evidence).
- **Next:** human review of PR #26.
- **Blockers:** none.

## Review cycles

| Cycle | Type (self/critic) | Reviewer | Outcome | Link |
|-------|--------------------|----------|---------|------|
|       |                    |          |         |      |

## Final validation evidence

- `uv run python scripts/validate_config.py` → `VALID .the-loop/config.yaml`,
  `VALID .the-loop/templates/config.yaml` (new `workflow.capabilitiesDir` key).
- `pre-commit run --all-files` → ruff (lint+format), pyright, pytest, markdownlint,
  schema validation all green — the exact hooks CI runs.
- R1: no file under `docs/specs/` (pre-issue-25) moved/renamed. R2/R3/R7: 8 capability
  docs + index exist with history rows covering all seven prior specs and this one.
  R5: ready-to-ship gate lists the fold-in item. R6: template, config key, manifest,
  skill/workflow/README wiring all present.
