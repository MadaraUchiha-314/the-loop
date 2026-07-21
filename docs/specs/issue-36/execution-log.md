---
type: execution-log
workItem: issue-36
phase: needs-review
status: in-progress
---

# Execution Log: templates become internal to the-loop

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-21 | @MadaraUchiha-314 | Bug: init duplicates internal templates into every project |
| design | 2026-07-21 | @MadaraUchiha-314 | Move to `skills/the-loop/templates/`, deprecate `.the-loop/templates/` |
| tasks-breakdown | 2026-07-21 | @MadaraUchiha-314 | 6-task DAG |
| implementation | 2026-07-21 |  | Implemented on `claude/github-issue-36-5ytag2` |
| needs-review | 2026-07-21 |  | PR opened; awaiting human review |
| complete |  |  |  |

## Progress entries

### 2026-07-21 — implemented

- **Phase:** implementation → needs-review
- **Did:**
  - `git mv .the-loop/templates skills/the-loop/templates`.
  - Manifest: dropped `templates:`, added `templatesDir` + `deprecated` cleanup entry.
  - `init.md`: scaffolds from internal templates, no longer copies the templates dir.
  - `upgrade-the-loop.md`: added deprecated-path cleanup step + report group.
  - Repointed all references (commands, `SKILL.md`, reference docs, README, architecture
    and capability docs) to `skills/the-loop/templates/`.
  - `dispatcher.py`: default template path constants + comments updated (built-in
    fallback unchanged and remains the source of truth in a project repo).
  - `config.schema.json`, `.the-loop/config.yaml`, and the config template: default
    template paths repointed.
- **Checkpoint/tests:** `ruff`, `pyright`, `pytest`, `markdownlint` — see final evidence.
- **Next:** open PR, request review.
- **Blockers:** none.

## Review cycles

| Cycle | Type (self/critic) | Reviewer | Outcome | Link |
|-------|--------------------|----------|---------|------|
|       |                    |          |         |      |

## Final validation evidence

Recorded on the PR: local gate output and `rg "\.the-loop/templates"` showing only the
intended references (manifest deprecated entry, upgrade command, and immutable historical
spec/decision records).
