---
description: Initialize "the-loop" in the current repository — scaffold .the-loop/, docs/, learnings/ and a validated config. Idempotent, non-clobbering, with drift detection.
argument-hint: "[--dry-run] [--monorepo-tool nx|pnpm|yarn|bun|none] [--ticketing github|jira]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: init

Initialize "the-loop" into the current project repository. **Idempotent and safe to
re-run:** it is driven entirely by the manifest, creates only what is missing, and
**never overwrites user-owned files**.

The **authoritative** source of what to create — and which files are managed vs.
user-owned — is `${CLAUDE_PLUGIN_ROOT}/.the-loop/manifest.yaml` (each entry's
`managed: true|false`), with the templates under
`${CLAUDE_PLUGIN_ROOT}/.the-loop/templates/`.

## Modes

- **`--dry-run`** — compute and print the report (below) **without writing anything**.
  Use it to preview an init or an upgrade safely.

## Steps

1. **Detect the project.** Inspect the repo to infer sensible defaults:
   - languages present (python / js / ts / go),
   - whether it looks like a monorepo (nx.json, pnpm-workspace.yaml, workspaces) and
     which tool — default Nx; support non-monorepo (`monorepo: false`),
   - existing package manager / test / lint / type-check tooling, mapped onto the
     `tooling` matrix (see the `the-loop` skill's `reference/tooling.md`),
   - the git remote / owner / repo for ticketing.
   Use these to pre-fill the config rather than blindly copying defaults.

2. **Reconcile against the manifest (idempotent, non-clobbering).** For every managed
   path, classify it and act:
   - **missing** → create it (from the template/default);
   - **present & `managed: false`** (user-owned) → **never overwrite**; leave it, note it;
   - **present & `managed: true` but drifted** from the current template/schema → **do
     not clobber**: diff and *suggest* the change (or apply only with explicit consent);
   - **present & up to date** → skip.
   Create the following where missing (never overwrite user-owned files):
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

6. **Wire local hooks & CI parity.** Set up pre-commit / pre-push hooks that run the
   `hooks.preCommit` / `hooks.prePush` steps (lint, typecheck, unit-test) using the
   configured tooling, and ensure CI invokes the SAME root commands (see
   `reference/tooling.md` → "CI/CD must use exactly the same tooling as local"). Only
   scaffold what the project doesn't already have.

7. **Report.** End with a short summary grouped as **created / skipped (up to date) /
   drifted (suggested) / needs-user** (files or config gaps the user must fill), then the
   immediate next action (`/the-loop:work-on <ticket>` or `/the-loop:new-requirement`).
   Under `--dry-run`, print exactly this report and write nothing.

Respect existing files. This command is idempotent, non-clobbering, and safe to re-run —
which is what makes it trustworthy to run on someone's repository.
