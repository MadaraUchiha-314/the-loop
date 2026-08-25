---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#213"
phase: requirements-definition
status: in-progress
---

# Execution Log: choose the model per loop — outer vs inner

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-24 | @MadaraUchiha-314 | full graph, boxes untouched; `pr-sessions-cross-repository` |
| requirements-definition | 2026-08-24 |  | `requirements.md` derived from the ticket |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| — | outer loop iterates on the work item itself (no spec-chain PR) | n/a |

## Progress entries

### 2026-08-24 — requirements drafted

- **Phase:** requirements-definition
- **Read first:** `cli/the_loop/webhook/dispatcher.py` (`_spawn_for`, `_spawn_endpoint`,
  `_try_resume`, and the `inner` flag at line 1851), `cli/the_loop/runner.py`
  (`spawn_in` → `interactive_argv`), `cli/the_loop/harness/base.py` (`model_flag`,
  applied today only by `oneshot_argv`), `.the-loop/cli-config.yaml`.
- **Finding that shaped the spec:** the outer/inner distinction already exists in the
  dispatcher and the model flag already exists on the adapters — the gap is only that
  the interactive argv builders never take a model.
- **Open questions** raised on the ticket: the config key's name, and whether the
  session-announcement comment should show the model.
