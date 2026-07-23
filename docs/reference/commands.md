# Commands

Names below use Claude Code's `/the-loop:` prefix; in Cursor the same commands appear
in the slash menu by filename (e.g. `/init`, `/work-on`).

## Superset commands

| Command | What it does |
|---------|--------------|
| `/the-loop:init` | Scaffold the-loop into the current repo (config, docs) via a guided, schema-driven onboarding with sensible defaults (`--defaults` skips the interaction). Idempotent. |
| `/the-loop:work-on <ticket>` | Run the whole 3-phase spec workflow (requirements → design → tasks → execute) on a GitHub issue / Jira id. Resumable per phase. **Superset of the granular commands below.** |
| `/the-loop:upgrade-the-loop` | Reconcile a project's the-loop files with the installed plugin version. |

## Granular per-phase commands

Run the same flow one step at a time:

| Command | What it does |
|---------|--------------|
| `/the-loop:brainstorm <title>` | *(Optional Phase 0)* Draft a free-form `brainstorm.md` scratchpad (the root artifact) for a fuzzy idea; iterate, then convert to requirements. |
| `/the-loop:new-requirement <title>` | Draft a `requirements.md` in a temporary `docs/specs/draft-<slug>/` folder **before a ticket exists** (converts a sibling `brainstorm.md` if present). |
| `/the-loop:create-ticket <path>` | Create the ticket from a `requirements.md`; promote `draft-<slug>/` → `docs/specs/<id>/`. |
| `/the-loop:create-design <id>` | Create `design.md` from the approved requirements (Phase 2). |
| `/the-loop:create-tasks-plan <id>` | Create the `tasks.md` DAG from requirements + design (Phase 3). |
| `/the-loop:execute-tasks <id>` | Implement the task DAG; self-check; self/critic-review; present evidence. |
| `/the-loop:finish-tasks <id>` | Cleanup after all tasks complete (close the ticket; extensible). |
| `/the-loop:work-status <id>` | Read-only status from the specs, task checkmarks and execution log. |

See the [operating model](/operating-model/) reference for what happens
inside each phase, and the [CLI reference](/cli) for the separate `the-loop`
companion CLI commands (`gh-webhook`, `poll`, `sessions`, `events`, `scenarios`).
