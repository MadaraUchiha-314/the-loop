---
description: Initialize "the-loop" in the current repository — scaffold .the-loop/, docs/, learnings/ and a validated config.
argument-hint: "[--monorepo-tool nx|pnpm|yarn|bun|none] [--ticketing github|jira]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: init

Initialize "the-loop" into the current project repository.

Source of truth for what to create is `${CLAUDE_PLUGIN_ROOT}/.the-loop/manifest.yaml`
and the templates under `${CLAUDE_PLUGIN_ROOT}/.the-loop/templates/`.

## Steps

1. **Detect the project.** Inspect the repo to infer sensible defaults:
   - languages present (python / js / ts / go),
   - whether it looks like a monorepo (nx.json, pnpm-workspace.yaml, workspaces),
   - the git remote / owner / repo for ticketing.
   Use these to pre-fill the config rather than blindly copying defaults.

2. **Create the structure** (skip anything that already exists; never overwrite
   user-owned files):
   - `.the-loop/config.yaml` — from the template, with detected defaults applied.
   - `.the-loop/config.schema.json` — copy of the schema.
   - `.the-loop/manifest.yaml` — the manifest.
   - `.the-loop/external-tools.md` and `.the-loop/collaborators.yaml` — from templates (user-owned).
   - `.the-loop/templates/` — the work-item & process templates.
   - `docs/architecture/architecture.md`, `docs/decisions/decisions.md`,
     `docs/specs/` (per-work-item Kiro specs + execution logs).
   - `learnings/learnings.md`.

3. **Create phase labels/tags** in the ticketing system for the workflow state
   machine — one per `workflow.phases`, named `<workflow.phaseLabelPrefix><phase>`
   (e.g. `loop:requirements-definition`, `loop:design`, … `loop:complete`). On GitHub
   create issue labels; on Jira create the equivalent statuses/labels. Skip any that
   already exist.

4. **Validate** the generated `.the-loop/config.yaml` against
   `.the-loop/config.schema.json`. Report any gaps the user must fill (e.g. empty
   `personas`, `ticketing.github.owner`).

5. **Confirm collaborators & personas.** If `personas`/collaborators are empty, ask
   the user (via a ticket comment if a ticket exists, otherwise interactively) to
   define at least one approver. RULE: every decision needs a paper trail.

6. **Summarize** what was created and the immediate next action
   (`/the-loop:work-on <ticket>`).

Respect existing files. This command is idempotent and safe to re-run.
